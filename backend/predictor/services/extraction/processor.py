"""Orchestrates source-document processing (Phase 3).

``SourceProcessingService`` turns an uploaded syllabus or exam paper into an
``ExtractionRun`` with ``ExtractionChunk`` rows and (for papers) individual
``Question`` rows. It is idempotent (same file hash returns the existing
successful run), concurrency-guarded (a fresh ``PROCESSING`` run blocks a
second request), and honest about failures (``FAILED`` / ``OCR_REQUIRED``
never set ``processed=True``).

Processing is synchronous; there is no Celery/Redis and no background
thread. A ``PROCESSING`` run older than ``EXTRACTION_STALE_MINUTES`` is
treated as interrupted and can be retried.
"""

import logging
from typing import Dict, List, Optional, Tuple

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ...models import (
    ExamPaper,
    ExtractionChunk,
    ExtractionRun,
    Question,
)
from .llm_parser import llm_fallback_enabled, parse_questions_llm
from .ocr import get_ocr_engine
from .question_parser import apply_ocr_confidence, parse_questions
from .text import extract_document, resolve_location
from .types import (
    ERROR_INTERRUPTED,
    ERROR_OCR_REQUIRED,
    ERROR_PARSER,
    METHOD_MIXED,
    METHOD_OCR,
    ExtractedQuestion,
)
from .validation import check_document_file, resolve_safe_path, sha256_file

logger = logging.getLogger(__name__)

_PREVIEW_CHARS = 2000


class ProcessingInProgress(Exception):
    """Raised when a fresh PROCESSING run already exists for a source."""

    def __init__(self, run: ExtractionRun):
        super().__init__("Processing is already in progress.")
        self.run = run


class SourceProcessingService:
    """Process one source document into traceable chunks and questions."""

    def process(
        self,
        document,
        source_type: str,
        force: bool = False,
    ) -> Tuple[ExtractionRun, str]:
        """Process ``document`` (a Syllabus or ExamPaper).

        Returns ``(run, outcome)`` where outcome is one of ``created``,
        ``existing`` (idempotent hit), ``conflict`` (another run is active).
        Raises no expected exceptions; failures are recorded on the run.
        """
        file_check = check_document_file(document.file)
        if not file_check.ok:
            run = self._record_failure(
                document, source_type, file_check.error_code,
                file_check.error_message,
            )
            return run, "created"

        file_hash = file_check.file_hash
        self._store_hash(document, file_hash)

        if not force:
            existing = self._find_successful_run(
                document, source_type, file_hash
            )
            if existing:
                return existing, "existing"

        # Concurrency guard: lock the document row, inspect active runs.
        with transaction.atomic():
            self._lock_document(document)
            active = self._find_active_run(document, source_type)
            if active is not None:
                if self._is_fresh(active):
                    return active, "conflict"
                self._mark_interrupted(active)

            is_syllabus = source_type == ExtractionRun.SOURCE_SYLLABUS
            run = ExtractionRun.objects.create(
                source_type=source_type,
                syllabus=document if is_syllabus else None,
                exam_paper=None if is_syllabus else document,
                file_hash=file_hash,
                status=ExtractionRun.STATUS_PROCESSING,
                started_at=timezone.now(),
            )
            self._set_doc_status(
                document, "PROCESSING", started_at=run.started_at
            )

        return self._execute(run, document, source_type, file_check), "created"

    # -- idempotency / concurrency ----------------------------------------

    def _find_successful_run(
        self, document, source_type: str, file_hash: str
    ) -> Optional[ExtractionRun]:
        qs = ExtractionRun.objects.filter(
            source_type=source_type, file_hash=file_hash,
            status__in=[
                ExtractionRun.STATUS_PROCESSED,
                ExtractionRun.STATUS_NEEDS_REVIEW,
            ],
        )
        qs = self._scope_to_document(qs, document, source_type)
        return qs.order_by("-created_at").first()

    def _find_active_run(
        self, document, source_type: str
    ) -> Optional[ExtractionRun]:
        qs = ExtractionRun.objects.filter(
            source_type=source_type, status=ExtractionRun.STATUS_PROCESSING
        )
        qs = self._scope_to_document(qs, document, source_type)
        return qs.order_by("-created_at").first()

    @staticmethod
    def _scope_to_document(qs, document, source_type: str):
        if source_type == ExtractionRun.SOURCE_SYLLABUS:
            return qs.filter(syllabus=document)
        return qs.filter(exam_paper=document)

    @staticmethod
    def _is_fresh(run: ExtractionRun) -> bool:
        from django.conf import settings

        if run.started_at is None:
            return True
        stale = getattr(settings, "EXTRACTION_STALE_MINUTES", 15)
        age = (timezone.now() - run.started_at).total_seconds() / 60.0
        return age < stale

    @staticmethod
    def _mark_interrupted(run: ExtractionRun) -> None:
        run.status = ExtractionRun.STATUS_FAILED
        run.error_code = ERROR_INTERRUPTED
        run.error_message = "Processing was interrupted. You can retry."
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error_code", "error_message", "finished_at"])

    @staticmethod
    def _lock_document(document) -> None:
        """Lock the source row so concurrent process calls serialize."""
        model = type(document)
        try:
            model.objects.select_for_update().get(pk=document.pk)
        except Exception:  # select_for_update unsupported on some backends
            pass

    # -- execution ---------------------------------------------------------

    def _execute(
        self, run: ExtractionRun, document, source_type: str, file_check
    ) -> ExtractionRun:
        path, path_err = resolve_safe_path(document.file)
        if path_err:
            return self._finalize_failure(
                run, document, "file_missing", "The source file is missing."
            )

        # Guard against the file changing between hash and parse.
        rehash = sha256_file(path)
        if rehash != run.file_hash:
            return self._finalize_failure(
                run, document, ERROR_PARSER,
                "The file changed while it was being processed. Retry.",
            )

        extraction = extract_document(
            document.file, source_type, document.pk, run.file_hash
        )
        if extraction.error_code:
            return self._finalize_failure(
                run, document, extraction.error_code, extraction.error_message
            )

        # OCR handling for low-text / scanned PDFs.
        if extraction.ocr_required:
            run_result = self._apply_ocr(run, document, path, extraction)
            if run_result is not None:
                return run_result  # OCR_REQUIRED (engine unavailable)

        # Parse questions (papers only; syllabus stores text/chunks only).
        questions: List[ExtractedQuestion] = []
        if source_type == ExtractionRun.SOURCE_EXAM_PAPER:
            questions = self._parse_questions(extraction, run)

        # Persist chunks and questions atomically.
        try:
            with transaction.atomic():
                chunk_map = self._persist_chunks(run, extraction)
                n_chunks = len(extraction.chunks)
                for q in questions:
                    _, chunk_idx, ref = resolve_location(
                        extraction.chunks, q.char_start
                    )
                    if chunk_idx is not None and chunk_idx < n_chunks:
                        q.page_number = extraction.chunks[chunk_idx].page_number
                    q.chunk_index = chunk_idx
                    q.page_reference = ref
                if source_type == ExtractionRun.SOURCE_EXAM_PAPER:
                    question_count = self._persist_questions(
                        run, document, extraction, questions, chunk_map
                    )
                else:
                    question_count = 0
                self._finalize_success(
                    run, document, extraction, questions, question_count
                )
        except Exception:
            logger.exception("Persistence failed for run %s", run.pk)
            return self._finalize_failure(
                run, document, ERROR_PARSER,
                "Saving the extracted data failed. Retry.",
            )
        self._index_for_retrieval(document)
        return run

    def _index_for_retrieval(self, document) -> None:
        """Phase 4: keep the notebook's RAG chunks in step (failure-isolated).

        Runs *after* the extraction transaction commits, never inside it, and
        never changes the outcome of extraction: a missing key, an unreachable
        provider or a missing vector store is logged and swallowed.
        """
        notebook = document.notebook
        if notebook is None:
            return
        if not getattr(settings, "EMBEDDING_AUTO_INDEX", True):
            return
        try:
            from ..rag import indexing

            result = indexing.index_notebook(notebook, embed=True)
        except Exception as exc:  # noqa: BLE001 - extraction must not fail here
            # RAG errors carry safe messages; anything else is a local bug, so
            # the traceback is useful and cannot echo uploaded text.
            logger.warning(
                "RAG indexing failed for notebook %s: %s",
                notebook.pk, type(exc).__name__, exc_info=True,
            )
            return
        logger.info(
            "RAG indexing notebook=%s chunks=%s embedded=%s failed=%s "
            "embed_skipped=%s",
            notebook.pk, result.get("sync", {}).get("chunks"),
            result.get("embed", {}).get("embedded"),
            result.get("embed", {}).get("failed"),
            result.get("embed", {}).get("skipped"),
        )

    def _apply_ocr(
        self, run: ExtractionRun, document, path: str, extraction
    ) -> Optional[ExtractionRun]:
        """Run OCR on low-text pages. Returns a run if OCR is unavailable."""
        engine = get_ocr_engine()
        if not engine.is_available():
            extraction.warnings.append("ocr_engine_unavailable")
            run.status = ExtractionRun.STATUS_OCR_REQUIRED
            run.ocr_required = True
            run.error_code = ERROR_OCR_REQUIRED
            run.error_message = (
                "This PDF appears to be scanned or image-only. "
                "No OCR engine is installed, so text extraction is "
                "incomplete. Install Tesseract to enable local OCR."
            )
            run.warnings = extraction.warnings
            run.low_text_pages = extraction.low_text_pages
            run.extraction_method = extraction.method
            run.page_count = extraction.page_count
            run.chunk_count = len(extraction.chunks)
            run.total_chars = len(extraction.full_text)
            self._persist_chunks(run, extraction)
            self._finalize_run_fields(
                run, document, ExtractionRun.STATUS_OCR_REQUIRED
            )
            return run

        ocr_confidences: Dict[Optional[int], Optional[float]] = {}
        any_ocr = False
        for chunk in extraction.chunks:
            if not chunk.is_low_text or chunk.page_number is None:
                continue
            result = engine.extract_page(path, chunk.page_number)
            if result.text.strip():
                chunk.text = result.text.strip()
                chunk.method = METHOD_OCR
                chunk.confidence = result.confidence
                chunk.warnings = list(chunk.warnings) + list(result.warnings)
                ocr_confidences[chunk.page_number] = result.confidence
                any_ocr = True
            else:
                chunk.warnings = list(chunk.warnings) + list(result.warnings)
                ocr_confidences[chunk.page_number] = None

        # Rebuild full text with OCR-filled chunks.
        from .text import _reconstruct

        extraction.full_text = _reconstruct(extraction.chunks)
        extraction.total_chars = len(extraction.full_text)
        if any_ocr:
            extraction.method = (
                METHOD_MIXED if extraction.method != METHOD_OCR else METHOD_OCR
            )
        # Carried for the question-confidence pass.
        extraction.ocr_confidences = ocr_confidences
        extraction.warnings.append("ocr_applied")
        # We have text now; confidence may still flag review per-question.
        extraction.ocr_required = False
        return None

    def _parse_questions(
        self, extraction, run: ExtractionRun
    ) -> List[ExtractedQuestion]:
        from django.conf import settings

        questions = parse_questions(extraction.full_text)
        ocr_confs = getattr(extraction, "ocr_confidences", None) or {}
        review_threshold = getattr(settings, "EXTRACTION_REVIEW_CONFIDENCE", 0.7)
        ocr_min = getattr(settings, "EXTRACTION_OCR_MIN_CONFIDENCE", 0.6)
        questions = apply_ocr_confidence(
            questions, ocr_confs, review_threshold, ocr_min
        )

        # LLM fallback when rule parsing found nothing usable.
        if not questions and llm_fallback_enabled():
            llm_qs = parse_questions_llm(
                extraction.full_text, extraction.page_count
            )
            if llm_qs:
                questions = llm_qs
                extraction.warnings.append("llm_assisted_parsing")
            else:
                extraction.warnings.append("llm_parse_failed")
        elif questions:
            low = [q for q in questions if q.confidence < review_threshold]
            if (
                low
                and len(low) == len(questions)
                and llm_fallback_enabled()
            ):
                llm_qs = parse_questions_llm(
                    extraction.full_text, extraction.page_count
                )
                if llm_qs:
                    questions = llm_qs
                    extraction.warnings.append("llm_assisted_parsing")
        return questions

    # -- persistence -------------------------------------------------------

    def _persist_chunks(
        self, run: ExtractionRun, extraction
    ) -> Dict[int, ExtractionChunk]:
        mapping: Dict[int, ExtractionChunk] = {}
        for chunk in extraction.chunks:
            obj = ExtractionChunk.objects.create(
                extraction=run,
                chunk_index=chunk.chunk_index,
                page_number=chunk.page_number,
                kind=chunk.kind,
                text=chunk.text,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                method=chunk.method,
                confidence=chunk.confidence,
                is_low_text=chunk.is_low_text,
                warnings=chunk.warnings,
            )
            mapping[chunk.chunk_index] = obj
        return mapping

    def _persist_questions(
        self,
        run: ExtractionRun,
        document: ExamPaper,
        extraction,
        questions: List[ExtractedQuestion],
        chunk_map: Dict[int, ExtractionChunk],
    ) -> int:
        touched: List[int] = []
        parent_pks: Dict[str, int] = {}
        subpart_qs: List[ExtractedQuestion] = []

        for q in questions:
            if q.parent_number:
                subpart_qs.append(q)
                continue
            obj = self._upsert_question(run, document, q, chunk_map)
            parent_pks[q.question_number] = obj.pk
            touched.append(obj.pk)

        for q in subpart_qs:
            obj = self._upsert_question(run, document, q, chunk_map)
            parent_pk = parent_pks.get(q.parent_number)
            if parent_pk and obj.parent_question_id != parent_pk:
                obj.parent_question_id = parent_pk
                obj.save(update_fields=["parent_question"])
            touched.append(obj.pk)

        # Remove stale auto-extracted questions from a previous version.
        prev_run = (
            ExtractionRun.objects.filter(
                exam_paper=document,
                status__in=[
                    ExtractionRun.STATUS_PROCESSED,
                    ExtractionRun.STATUS_NEEDS_REVIEW,
                ],
            )
            .exclude(pk=run.pk)
            .order_by("-created_at")
            .first()
        )
        if prev_run is not None:
            Question.objects.filter(
                exam_paper=document, source_run=prev_run,
                extraction_status=Question.STATUS_EXTRACTED,
            ).exclude(pk__in=touched).delete()

        return len(touched)

    def _upsert_question(
        self,
        run: ExtractionRun,
        document: ExamPaper,
        q: ExtractedQuestion,
        chunk_map: Dict[int, ExtractionChunk],
    ) -> Question:
        from django.conf import settings as django_settings

        review_threshold = getattr(
            django_settings, "EXTRACTION_REVIEW_CONFIDENCE", 0.7
        )
        needs_review = (
            q.confidence < review_threshold
            or "ocr_low_confidence" in q.warnings
            or "ocr_math_review" in q.warnings
        )
        status = (
            Question.STATUS_NEEDS_REVIEW if needs_review
            else Question.STATUS_EXTRACTED
        )
        source_chunk = (
            chunk_map.get(q.chunk_index)
            if q.chunk_index is not None
            else None
        )
        obj, _ = Question.objects.update_or_create(
            exam_paper=document,
            parent_number=q.parent_number,
            question_number=q.question_number,
            defaults={
                "raw_text": q.raw_text,
                "normalized_text": q.normalized_text,
                "page_reference": q.page_reference,
                "marks": q.marks,
                "question_type": q.question_type,
                "difficulty": q.difficulty,
                "options": q.options,
                "extraction_status": status,
                "extraction_confidence": q.confidence,
                "extraction_method": q.method,
                "extraction_warnings": q.warnings,
                "source_run": run,
                "source_chunk": source_chunk,
            },
        )
        return obj

    # -- finalization / helpers -------------------------------------------

    def _finalize_success(
        self,
        run: ExtractionRun,
        document,
        extraction,
        questions: List[ExtractedQuestion],
        question_count: int,
    ) -> None:
        review_needed = any(
            q.confidence < 0.7
            or "ocr_low_confidence" in q.warnings
            or "ocr_math_review" in q.warnings
            for q in questions
        ) or extraction.ocr_required

        if questions and review_needed:
            final = ExtractionRun.STATUS_NEEDS_REVIEW
        elif not questions and run.source_type == ExtractionRun.SOURCE_EXAM_PAPER:
            # Paper produced text but no questions: needs a human look.
            final = ExtractionRun.STATUS_NEEDS_REVIEW
            extraction.warnings.append("no_questions_detected")
        else:
            final = ExtractionRun.STATUS_PROCESSED

        run.status = final
        run.extraction_method = extraction.method
        run.page_count = extraction.page_count
        run.chunk_count = len(extraction.chunks)
        run.total_chars = len(extraction.full_text)
        run.question_count = question_count
        run.low_text_pages = extraction.low_text_pages
        run.warnings = extraction.warnings
        run.ocr_required = extraction.ocr_required
        run.finished_at = timezone.now()
        run.save()

        self._finalize_run_fields(run, document, final, extraction, questions)

    def _finalize_failure(
        self, run: ExtractionRun, document, error_code: str, message: str
    ) -> ExtractionRun:
        run.status = ExtractionRun.STATUS_FAILED
        run.error_code = error_code
        run.error_message = message
        run.finished_at = timezone.now()
        run.save()
        self._finalize_run_fields(run, document, ExtractionRun.STATUS_FAILED)
        return run

    def _finalize_run_fields(
        self,
        run: ExtractionRun,
        document,
        status: str,
        extraction=None,
        questions: Optional[List[ExtractedQuestion]] = None,
    ) -> None:
        document.processing_status = status
        document.processing_error = (
            run.error_message if status == ExtractionRun.STATUS_FAILED else ""
        )
        document.processing_finished_at = timezone.now()
        document.processed = status == ExtractionRun.STATUS_PROCESSED
        if document.processed:
            document.processed_at = timezone.now()
        if extraction is not None:
            document.extracted_text = extraction.full_text[:_PREVIEW_CHARS]
            document.analysis_data = {
                **(document.analysis_data or {}),
                "extraction_run_id": run.pk,
                "extraction_method": extraction.method,
                "chunk_count": len(extraction.chunks),
                "page_count": extraction.page_count,
                "warnings": extraction.warnings,
            }
        if run.source_type == ExtractionRun.SOURCE_EXAM_PAPER:
            document.question_count = run.question_count
        document.save()

    def _record_failure(
        self, document, source_type: str, error_code: str, message: str
    ) -> ExtractionRun:
        is_syllabus = source_type == ExtractionRun.SOURCE_SYLLABUS
        run = ExtractionRun.objects.create(
            source_type=source_type,
            syllabus=document if is_syllabus else None,
            exam_paper=None if is_syllabus else document,
            file_hash="",
            status=ExtractionRun.STATUS_FAILED,
            error_code=error_code,
            error_message=message,
            started_at=timezone.now(),
            finished_at=timezone.now(),
        )
        self._finalize_run_fields(run, document, ExtractionRun.STATUS_FAILED)
        return run

    @staticmethod
    def _set_doc_status(document, status: str, started_at=None) -> None:
        document.processing_status = status
        document.processing_started_at = started_at or timezone.now()
        document.save(update_fields=[
            "processing_status", "processing_started_at",
        ])

    @staticmethod
    def _store_hash(document, file_hash: str) -> None:
        if document.content_hash != file_hash:
            document.content_hash = file_hash
            document.save(update_fields=["content_hash"])


def process_source(document, source_type: str, force: bool = False):
    """Module-level convenience wrapper used by the API and tests."""
    return SourceProcessingService().process(document, source_type, force=force)
