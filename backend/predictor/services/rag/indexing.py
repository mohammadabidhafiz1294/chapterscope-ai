"""Building and embedding ``DocumentChunk`` rows for one notebook (Phase 4).

Two phases, deliberately separable:

* :func:`sync_chunks` -- portable (runs on SQLite too): derives the desired set
  of retrievable passages from the notebook's syllabi, exam papers and
  questions, then upserts / deletes ``DocumentChunk`` rows to match it. Text is
  content-hashed, so an unchanged passage never loses its embedding status.
* :func:`embed_pending` -- needs PostgreSQL + a configured provider: sends
  ``PENDING`` / ``STALE`` chunks to the embedding backend and writes
  ``DocumentChunkEmbedding`` rows.

Neither phase edits or deletes source documents, questions or their text. A
provider failure only marks chunks ``FAILED`` with a machine-readable code and
leaves everything else exactly as it was.
"""

import logging
from collections import defaultdict

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ...models import (
    CourseNotebook,
    DocumentChunk,
    DocumentChunkEmbedding,
    ExamPaper,
    ExtractionRun,
    Question,
    Syllabus,
)
from . import embeddings, schema
from .embeddings import get_config
from .errors import RAGError

logger = logging.getLogger(__name__)

# Safe, machine-readable codes stored on DocumentChunk.embedding_error.
ERROR_INVALID_TEXT = 'invalid_text'

# Extraction runs whose text is real and worth indexing (a NEEDS_REVIEW run has
# genuine text, only its parsed questions need a human).
INDEXABLE_RUN_STATUSES = (
    ExtractionRun.STATUS_PROCESSED,
    ExtractionRun.STATUS_NEEDS_REVIEW,
)

# Passage sizing. `target` is the retrieval granularity; `maximum` is the hard
# cap enforced by the embedding contract (EMBEDDING_MAX_TEXT_CHARS).
_PASSAGE_TARGET_CHARS = 2000

# A source extraction chunk becomes `chunk_index * STRIDE + sub` so inserting a
# page never renumbers (and therefore never re-embeds) unrelated passages.
_INDEX_STRIDE = 1000

# Bounded metadata returned with search results.
_MAX_TOPICS = 20


def split_passages(text, *, target=_PASSAGE_TARGET_CHARS, maximum=None):
    """Split text into retrieval passages. Deterministic and order-preserving.

    Paragraphs are kept whole when possible and greedily packed up to
    ``target`` characters; a single oversized paragraph is cut at whitespace.
    Empty passages are dropped.
    """
    if maximum is None:
        maximum = max(
            target, int(getattr(settings, 'EMBEDDING_MAX_TEXT_CHARS', 8000))
        )
    target = max(1, min(target, maximum))

    cleaned = (text or '').replace('\r\n', '\n').replace('\r', '\n').strip()
    if not cleaned:
        return []

    passages = []
    current = ''
    for paragraph in cleaned.split('\n\n'):
        paragraph = ' '.join(
            chunk.strip() for chunk in paragraph.split('\n')
        ).strip()
        if not paragraph:
            continue
        for piece in _harden(paragraph, target):
            candidate = f'{current} {piece}'.strip() if current else piece
            if len(candidate) <= target:
                current = candidate
            else:
                if current:
                    passages.append(current)
                current = piece
    if current:
        passages.append(current)

    final = []
    for passage in passages:
        if len(passage) > maximum:
            final.extend(_harden(passage, maximum))
        else:
            final.append(passage)
    return [passage for passage in final if passage.strip()]


def _harden(text, size):
    """Cut ``text`` into pieces of at most ``size`` chars at word boundaries."""
    remaining = text.strip()
    while len(remaining) > size:
        cut = remaining.rfind(' ', 0, size + 1)
        if cut <= 0:
            cut = size
        yield remaining[:cut].rstrip()
        remaining = remaining[cut:].lstrip()
    if remaining:
        yield remaining


def _topic_names(names):
    topics = []
    for name in names or []:
        if isinstance(name, str) and name.strip() and name not in topics:
            topics.append(name.strip())
        if len(topics) >= _MAX_TOPICS:
            break
    return topics


def _topics_metadata(names):
    """Display topics plus a normalized copy used by the topic filter."""
    topics = _topic_names(names)
    return {
        'topics': topics,
        'topics_normalized': [topic.lower() for topic in topics],
    }


def _page_from_reference(reference):
    digits = ''.join(char for char in (reference or '') if char.isdigit())
    return int(digits) if digits else None


# ---------------------------------------------------------------------------
# Passage sources
# ---------------------------------------------------------------------------

def _run_passages(document, source_type, base_metadata):
    """Passages from the newest extraction run that actually has text."""
    lookups = {'status__in': INDEXABLE_RUN_STATUSES}
    if source_type == DocumentChunk.SOURCE_SYLLABUS:
        lookups['syllabus'] = document
    else:
        lookups['exam_paper'] = document
    runs = ExtractionRun.objects.filter(**lookups).order_by('-created_at')

    for run in runs:
        chunks = list(run.chunks.order_by('chunk_index'))
        if not chunks:
            continue
        passages = []
        for extraction_chunk in chunks:
            for sub, piece in enumerate(split_passages(extraction_chunk.text)):
                if not piece.strip():
                    continue
                passages.append({
                    'chunk_index': extraction_chunk.chunk_index * _INDEX_STRIDE + sub,
                    'text': piece,
                    'page_number': extraction_chunk.page_number,
                    'metadata': dict(
                        base_metadata,
                        run=run.pk,
                        kind=extraction_chunk.kind,
                        extraction_chunk=extraction_chunk.pk,
                    ),
                })
        if passages:
            return passages
    return []


def _text_passages(text, base_metadata):
    """Fallback passages built from a document's reconstructed full text."""
    metadata = dict(base_metadata, kind='TEXT')
    return [
        {
            'chunk_index': index,
            'text': piece,
            'page_number': None,
            'metadata': dict(metadata),
        }
        for index, piece in enumerate(split_passages(text))
        if piece.strip()
    ]


def _syllabus_specs(syllabus):
    metadata = {
        'document': syllabus.title,
        'subject': syllabus.subject,
        **_topics_metadata(syllabus.topics_covered),
    }
    passages = _run_passages(syllabus, DocumentChunk.SOURCE_SYLLABUS, metadata)
    if not passages:
        passages = _text_passages(syllabus.extracted_text, metadata)
    return [
        {
            'source_type': DocumentChunk.SOURCE_SYLLABUS,
            'syllabus': syllabus,
            'exam_paper': None,
            'question': None,
            'question_number': '',
            'parent_number': '',
            'year': None,
            **passage,
        }
        for passage in passages
    ]


def _question_specs(question):
    text = (
        (question.normalized_text or '').strip()
        or (question.raw_text or '').strip()
    )
    if not text:
        return []
    paper = question.exam_paper
    topics = [
        link.topic.name for link in question.topic_links.select_related('topic')
    ]
    metadata = {
        'document': paper.title,
        **_topics_metadata(topics),
        'marks': question.marks,
        'question_type': question.question_type,
        'difficulty': question.difficulty,
        'extraction_method': question.extraction_method,
    }
    return [
        {
            'source_type': DocumentChunk.SOURCE_QUESTION,
            'syllabus': None,
            'exam_paper': paper,
            'question': question,
            'question_number': question.question_number,
            'parent_number': question.parent_number,
            'year': question.year,
            'chunk_index': sub,
            'text': piece,
            'page_number': _page_from_reference(question.page_reference),
            'metadata': dict(metadata),
        }
        for sub, piece in enumerate(split_passages(text))
        if piece.strip()
    ]


def _paper_specs(paper):
    """Paper passages that are *not* already indexed as a question.

    Question text is only indexed once (as a QUESTION chunk), so a paper
    contributes its instructions, headings and any text no question covers.
    """
    claimed = set(
        Question.objects.filter(exam_paper=paper)
        .exclude(source_chunk=None)
        .values_list('source_chunk_id', flat=True)
    )
    metadata = {
        'document': paper.title,
        **_topics_metadata(paper.topics_covered),
    }
    passages = []
    for passage in _run_passages(paper, DocumentChunk.SOURCE_EXAM_PAPER, metadata):
        # `_run_passages` stride-encodes the source extraction chunk id.
        source_chunk_id = passage['chunk_index'] // _INDEX_STRIDE
        if source_chunk_id in claimed:
            continue
        passages.append({**passage, 'chunk_index': len(passages)})
    if not passages and not claimed:
        passages = _text_passages(paper.extracted_text, metadata)
    return [
        {
            'source_type': DocumentChunk.SOURCE_EXAM_PAPER,
            'syllabus': None,
            'exam_paper': paper,
            'question': None,
            'question_number': '',
            'parent_number': '',
            'year': paper.year,
            **passage,
        }
        for passage in passages
    ]


def _syllabus_specs_for_notebook(notebook):
    specs = []
    for syllabus in Syllabus.objects.filter(notebook=notebook):
        specs.extend(_syllabus_specs(syllabus))
    return specs


def _question_specs_for_notebook(notebook):
    specs = []
    questions = (
        Question.objects.filter(notebook=notebook)
        .select_related('exam_paper')
        .prefetch_related('topic_links__topic')
    )
    for question in questions:
        specs.extend(_question_specs(question))
    return specs


def _paper_specs_for_notebook(notebook):
    specs = []
    for paper in ExamPaper.objects.filter(notebook=notebook):
        specs.extend(_paper_specs(paper))
    return specs


# ---------------------------------------------------------------------------
# Phase 1: portable chunk sync
# ---------------------------------------------------------------------------

def sync_chunks(notebook: CourseNotebook) -> dict:
    """Make ``DocumentChunk`` rows match the notebook's current sources."""
    stats = {'created': 0, 'updated': 0, 'unchanged': 0, 'deleted': 0, 'chunks': 0}
    plans = (
        (DocumentChunk.SOURCE_SYLLABUS, _syllabus_specs_for_notebook(notebook)),
        (DocumentChunk.SOURCE_QUESTION, _question_specs_for_notebook(notebook)),
        (DocumentChunk.SOURCE_EXAM_PAPER, _paper_specs_for_notebook(notebook)),
    )
    for source_type, specs in plans:
        _apply_specs(notebook, source_type, specs, stats)
    stats['chunks'] = DocumentChunk.objects.filter(notebook=notebook).count()
    logger.info(
        'sync_chunks notebook=%s created=%d updated=%d unchanged=%d '
        'deleted=%d',
        notebook.pk, stats['created'], stats['updated'], stats['unchanged'],
        stats['deleted'],
    )
    return stats


def _apply_specs(notebook, source_type, specs, stats):
    existing = {
        chunk.source_key: chunk
        for chunk in DocumentChunk.objects.filter(
            notebook=notebook, source_type=source_type
        )
    }
    seen = set()
    for fields in specs:
        candidate = DocumentChunk(notebook=notebook, **fields)
        source_key = candidate.build_source_key()
        if not source_key or source_key in seen:
            # `source_key` is globally unique; a duplicate would mean two specs
            # claim the same identity, and the first one wins.
            continue
        seen.add(source_key)
        digest = DocumentChunk.hash_text(candidate.text)
        previous = existing.get(source_key)
        if previous is None:
            candidate.source_key = source_key
            candidate.content_hash = digest
            candidate.embedding_status = DocumentChunk.STATUS_PENDING
            candidate.save()
            stats['created'] += 1
        elif previous.content_hash != digest:
            _replace_text(previous, candidate, digest)
            stats['updated'] += 1
        else:
            _refresh_metadata(previous, candidate)
            stats['unchanged'] += 1

    stale = DocumentChunk.objects.filter(
        notebook=notebook, source_type=source_type
    ).exclude(source_key__in=seen)
    deleted, _ = stale.delete()
    stats['deleted'] += deleted or 0


def _replace_text(previous, candidate, digest):
    """Swap in new text and queue a fresh embedding; drop the old vector."""
    DocumentChunkEmbedding.objects.filter(chunk=previous).delete()
    previous.text = candidate.text
    previous.content_hash = digest
    previous.metadata = candidate.metadata
    previous.page_number = candidate.page_number
    previous.year = candidate.year
    previous.question_number = candidate.question_number
    previous.parent_number = candidate.parent_number
    previous.embedding_status = DocumentChunk.STATUS_PENDING
    previous.embedding_error = ''
    previous.save()


def _refresh_metadata(previous, candidate):
    """Update provenance that does not invalidate the stored vector."""
    changed = {}
    for name in (
        'metadata', 'page_number', 'year', 'question_number', 'parent_number'
    ):
        new_value = getattr(candidate, name)
        if getattr(previous, name) != new_value:
            # The row itself has to carry the new value: `update_fields` writes
            # whatever is in memory, so collecting it without assigning it
            # would save the old data back.
            setattr(previous, name, new_value)
            changed[name] = new_value
    if changed:
        previous.save(update_fields=list(changed) + ['updated_at'])


# ---------------------------------------------------------------------------
# Phase 2: PostgreSQL embedding
# ---------------------------------------------------------------------------

def embed_pending(notebook=None, *, limit=None, raise_on_error=False) -> dict:
    """Embed PENDING / STALE chunks. Never touches source rows or text."""
    stats = {
        'embedded': 0, 'failed': 0, 'batches': 0, 'skipped': None,
        'stopped': False, 'errors': [],
    }
    if not getattr(settings, 'EMBEDDING_ENABLED', True):
        stats['skipped'] = 'disabled'
        return stats
    if not schema.is_postgres():
        stats['skipped'] = 'not_postgres'
        return stats

    config = get_config()
    try:
        schema.ensure_vector_schema()
        dimension = schema.require_ready()
    except RAGError as error:
        stats['skipped'] = error.code
        stats['errors'].append(error.code)
        if raise_on_error:
            raise
        return stats

    pending = DocumentChunk.objects.filter(
        embedding_status__in=[
            DocumentChunk.STATUS_PENDING, DocumentChunk.STATUS_STALE
        ]
    ).order_by('source_key')
    if notebook is not None:
        pending = pending.filter(notebook=notebook)
    if limit:
        pending = pending[:int(limit)]
    chunks = list(pending)

    ready = []
    for chunk in chunks:
        text = chunk.text or ''
        if not text.strip() or len(text) > config.max_text_chars:
            _mark_failed([chunk], ERROR_INVALID_TEXT)
            stats['failed'] += 1
            stats['errors'].append(ERROR_INVALID_TEXT)
        else:
            ready.append(chunk)

    for start in range(0, len(ready), config.batch_size):
        batch = ready[start:start + config.batch_size]
        try:
            vectors = embeddings.embed_documents([chunk.text for chunk in batch])
        except RAGError as error:
            _mark_failed(batch, error.code)
            stats['failed'] += len(batch)
            stats['errors'].append(error.code)
            stats['stopped'] = True
            if raise_on_error:
                raise
            logger.warning(
                'embed_pending stopped after %s (batch=%d)',
                error.code, len(batch),
            )
            return stats
        _write_vectors(batch, vectors, config.model, dimension, stats)
        stats['batches'] += 1

    logger.info(
        'embed_pending notebook=%s embedded=%d failed=%d batches=%d',
        notebook.pk if notebook else None, stats['embedded'],
        stats['failed'], stats['batches'],
    )
    return stats


def _write_vectors(chunks, vectors, model, dimension, stats):
    from .errors import DimensionMismatch

    if len(vectors) != len(chunks):
        raise ValueError(
            f'provider returned {len(vectors)} vectors for {len(chunks)} chunks'
        )
    rows = []
    for chunk, vector in zip(chunks, vectors):
        if len(vector) != dimension:
            raise DimensionMismatch(
                f'Embedding has {len(vector)} dimensions but the vector column '
                f'is {dimension}.'
            )
        rows.append(DocumentChunkEmbedding(
            chunk=chunk,
            embedding=vector,
            embedding_model=model,
            dim=dimension,
            content_hash=chunk.content_hash,
        ))

    now = timezone.now()
    with transaction.atomic():
        DocumentChunkEmbedding.objects.bulk_create(
            rows,
            update_conflicts=True,
            update_fields=[
                'embedding', 'embedding_model', 'dim', 'content_hash',
                'updated_at',
            ],
            unique_fields=['chunk'],
        )
        # Only flip rows whose text is still what we just embedded, so a
        # concurrent re-sync can never be marked up to date by stale work.
        by_hash = defaultdict(list)
        for chunk in chunks:
            by_hash[chunk.content_hash].append(chunk.pk)
        for digest, primary_keys in by_hash.items():
            DocumentChunk.objects.filter(
                pk__in=primary_keys, content_hash=digest
            ).update(
                embedding_status=DocumentChunk.STATUS_EMBEDDED,
                embedding_model=model,
                embedding_dim=dimension,
                embedded_at=now,
                embedding_error='',
            )
    stats['embedded'] += len(chunks)


def _mark_failed(chunks, code):
    if not chunks:
        return
    DocumentChunk.objects.filter(pk__in=[chunk.pk for chunk in chunks]).update(
        embedding_status=DocumentChunk.STATUS_FAILED,
        embedding_error=code[:64],
    )


def reset_vectors() -> dict:
    """Drop every stored vector and queue all chunks for re-embedding.

    Source text, provenance and metadata are untouched. Used after a model or
    dimension change (``manage.py index_rag --reset-vectors``).
    """
    if not schema.is_postgres():
        return {'skipped': 'not_postgres'}
    outcome = schema.ensure_vector_schema()
    removed, _ = DocumentChunkEmbedding.objects.all().delete()
    queued = DocumentChunk.objects.exclude(
        embedding_status=DocumentChunk.STATUS_PENDING
    ).update(
        embedding_status=DocumentChunk.STATUS_PENDING,
        embedding_error='',
        embedding_model='',
        embedding_dim=None,
        embedded_at=None,
    )
    logger.warning(
        'reset_vectors schema=%s removed=%d queued=%d', outcome, removed, queued
    )
    return {'schema': outcome, 'removed': removed, 'queued': queued}


def index_notebook(notebook: CourseNotebook, *, embed: bool = True) -> dict:
    """Sync chunks and (optionally) embed whatever is pending.

    Failure-isolated: provider and schema errors are reported inside the
    returned dict instead of raised, so callers in a request path are safe.
    """
    result = {'sync': sync_chunks(notebook)}
    if embed:
        result['embed'] = embed_pending(notebook, raise_on_error=False)
    else:
        result['embed'] = {'skipped': 'not_requested'}
    return result
