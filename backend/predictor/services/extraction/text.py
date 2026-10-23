"""Text extraction from stored documents into ordered, bounded chunks.

Wraps the existing ``PDFExtractor`` / ``DOCXExtractor`` services (no
duplicated parser logic) and adds plain-TXT handling. Produces a
``DocumentExtraction`` with one chunk per PDF page, per DOCX paragraph or
table, or a single blob for TXT, plus a reconstructed full text with char
spans so questions can be mapped back to their exact source location.

Nothing is silently discarded: tables, formulas, units and figure references
stay in the chunk text; detection of such constructs raises warnings instead
of stripping content.
"""

import logging
import re
from typing import List, Optional, Tuple

from django.conf import settings

from ...utils.docx_extractor import DOCXExtractor
from ...utils.pdf_extractor import PDFExtractor
from .types import (
    ERROR_CHAR_LIMIT,
    ERROR_CORRUPT,
    ERROR_EMPTY,
    KIND_PAGE,
    KIND_PARAGRAPH,
    KIND_TABLE,
    KIND_TEXT,
    METHOD_DOCX_TEXT,
    METHOD_PLAIN_TEXT,
    METHOD_PDF_TEXT,
    ChunkText,
    DocumentExtraction,
)

logger = logging.getLogger(__name__)

# Content markers we refuse to strip; their presence only raises a warning.
_FORMULA_RE = re.compile(
    r"(?:\\frac|\\sqrt|\\int|\\sum|\\prod|\\begin\{|"
    r"[ΩΩμλπθφαβγδ]|[∫∑√±×÷≤≥≈∞²³]|"
    r"\b[A-Za-z]\s*=\s*|\^2\b|d[A-Za-z]/d[A-Za-z])"
)
_FIGURE_RE = re.compile(r"\b(?:Fig(?:ure)?\.?|Table|Eq(?:uation)?\.?)\s*\d+")
_UNIT_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*"
    r"(?:kg|mg|g|m|cm|mm|km|nm|pm|um|µm|s|ms|us|ns|N|J|eV|keV|MeV|W|kW|MW|"
    r"V|mV|kV|A|mA|Ω|ohm|Pa|kPa|MPa|K|mol|Hz|kHz|MHz|GHz|THz|°C|%|L|mL)\b"
)


def _content_warnings(text: str) -> List[str]:
    """Detect formulas / figure refs / units so they are never lost silently."""
    warnings: List[str] = []
    if _FORMULA_RE.search(text):
        warnings.append("formula_detected")
    if _FIGURE_RE.search(text):
        warnings.append("figure_or_table_reference")
    if _UNIT_RE.search(text):
        warnings.append("units_detected")
    return warnings


def _non_ws_len(text: str) -> int:
    return len(re.sub(r"\s", "", text))


def extract_document(
    django_file,
    source_type: str,
    source_id: int,
    file_hash: str,
) -> DocumentExtraction:
    """Extract a stored document into a DocumentExtraction.

    Dispatches on file extension. ``django_file`` must already have passed
    ``validation.check_document_file``. Returns a DocumentExtraction whose
    ``error_code`` is set on failure (never raises for expected errors).
    """
    name = getattr(django_file, "name", "") or ""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    path = django_file.path

    result = DocumentExtraction(
        source_type=source_type, source_id=source_id, file_hash=file_hash
    )
    max_chars = getattr(settings, "EXTRACTION_MAX_CHARS", 2_000_000)

    if ext == "pdf":
        _extract_pdf(path, result)
    elif ext == "docx":
        _extract_docx(path, result)
    elif ext == "txt":
        _extract_txt(path, result)
    else:
        result.error_code = ERROR_CORRUPT
        result.error_message = f"Unsupported file type '{ext}'."

    if result.error_code:
        return result

    # An empty full_text is only a hard failure when no page was flagged as
    # low-text (scanned / image-only PDFs legitimately extract zero chars and
    # are handed to the OCR stage by the processor, not failed here).
    if not result.chunks or (
        not result.full_text.strip() and not result.low_text_pages
    ):
        result.error_code = ERROR_EMPTY
        result.error_message = "No text could be extracted from the file."
        return result

    if len(result.full_text) > max_chars:
        result.error_code = ERROR_CHAR_LIMIT
        result.error_message = (
            f"The extracted text exceeds the limit of {max_chars} characters."
        )
        return result

    result.total_chars = len(result.full_text)
    return result


def _reconstruct(chunks: List[ChunkText]) -> str:
    """Join chunk texts with a blank line and record char spans."""
    parts: List[str] = []
    offset = 0
    for chunk in chunks:
        chunk.char_start = offset
        chunk.char_end = offset + len(chunk.text)
        parts.append(chunk.text)
        offset = chunk.char_end + 2  # + "\n\n"
    return "\n\n".join(parts)


def _extract_pdf(path: str, result: DocumentExtraction) -> None:
    extractor = PDFExtractor()
    parsed = extractor.extract_text(path)
    if not parsed.get("success"):
        result.error_code = ERROR_CORRUPT
        result.error_message = "The PDF could not be read."
        return

    total_pages = parsed.get("total_pages", 0)
    result.page_count = total_pages
    min_chars = getattr(settings, "EXTRACTION_OCR_MIN_CHARS", 40)

    # Index extracted pages by number; pages that yielded no text are absent.
    by_page = {p["page_number"]: p for p in parsed.get("pages", [])}

    chunks: List[ChunkText] = []
    low_pages: List[int] = []

    for page_num in range(1, total_pages + 1):
        page = by_page.get(page_num)
        text = (page or {}).get("content", "")
        is_low = _non_ws_len(text) < min_chars
        if is_low:
            low_pages.append(page_num)
        chunk_warnings = _content_warnings(text) if text else []
        chunks.append(
            ChunkText(
                chunk_index=len(chunks),
                text=text,
                kind=KIND_PAGE,
                page_number=page_num,
                method=METHOD_PDF_TEXT,
                is_low_text=is_low,
                warnings=chunk_warnings,
            )
        )

    result.chunks = chunks
    result.low_text_pages = low_pages
    result.full_text = _reconstruct(chunks)
    result.method = METHOD_PDF_TEXT
    if low_pages:
        result.warnings.append("low_text_pages_detected")
        result.ocr_required = True


def _extract_docx(path: str, result: DocumentExtraction) -> None:
    extractor = DOCXExtractor()
    parsed = extractor.extract_text(path)
    if not parsed.get("success"):
        result.error_code = ERROR_CORRUPT
        result.error_message = "The DOCX document could not be read."
        return

    chunks: List[ChunkText] = []
    for para in parsed.get("paragraphs", []):
        text = para.get("content", "")
        if not text.strip():
            continue
        chunk_warnings = _content_warnings(text)
        chunks.append(
            ChunkText(
                chunk_index=len(chunks),
                text=text,
                kind=KIND_PARAGRAPH,
                page_number=None,
                method=METHOD_DOCX_TEXT,
                warnings=chunk_warnings,
            )
        )
    for table in parsed.get("tables", []):
        text = table.get("content", "")
        if not text.strip():
            continue
        chunk_warnings = _content_warnings(text)
        chunk_warnings.append("table_structure_flattened")
        chunks.append(
            ChunkText(
                chunk_index=len(chunks),
                text=text,
                kind=KIND_TABLE,
                page_number=None,
                method=METHOD_DOCX_TEXT,
                warnings=chunk_warnings,
            )
        )

    result.chunks = chunks
    result.page_count = 0  # DOCX has no page concept here
    result.full_text = _reconstruct(chunks)
    result.method = METHOD_DOCX_TEXT
    # DOCX extraction is deterministic; no low-text / OCR detection applies.


def _extract_txt(path: str, result: DocumentExtraction) -> None:
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            text = handle.read()
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("TXT read failed: %s", exc)
        result.error_code = ERROR_CORRUPT
        result.error_message = "The text file could not be read."
        return

    if not text.strip():
        result.error_code = ERROR_EMPTY
        result.error_message = "The text file is empty."
        return

    chunk_warnings = _content_warnings(text)
    chunk = ChunkText(
        chunk_index=0,
        text=text,
        kind=KIND_TEXT,
        page_number=None,
        method=METHOD_PLAIN_TEXT,
        warnings=chunk_warnings,
    )
    result.chunks = [chunk]
    result.page_count = 0
    result.full_text = _reconstruct([chunk])
    result.method = METHOD_PLAIN_TEXT


def resolve_location(
    chunks: List[ChunkText], char_offset: int
) -> Tuple[Optional[int], Optional[int], str]:
    """Map a char offset in the full text to (page_number, chunk_index, ref).

    ``page_number`` is None for non-paginated formats. ``ref`` is the
    human-readable page reference (e.g. "3" or "3-4"); empty when unknown.
    """
    start_chunk: Optional[int] = None
    end_chunk: Optional[int] = None
    for idx, chunk in enumerate(chunks):
        if chunk.char_start <= char_offset <= chunk.char_end:
            start_chunk = idx
            end_chunk = idx
            break
    if start_chunk is None:
        # Offset falls in the separator after the last chunk.
        for idx, chunk in enumerate(chunks):
            if char_offset <= chunk.char_end:
                start_chunk = idx
                end_chunk = idx
                break
    if start_chunk is None:
        start_chunk = 0
        end_chunk = 0

    start_page = chunks[start_chunk].page_number
    end_page = chunks[end_chunk].page_number
    if start_page is not None and end_page is not None:
        ref = str(start_page) if start_page == end_page else f"{start_page}-{end_page}"
    else:
        ref = ""
    return start_page, start_chunk, ref
