"""Deterministic-first retrieval of the two separately labelled contexts.

Both contexts are filtered to exactly one notebook and the selected topic;
a foreign notebook or another topic's material can never enter the prompt.

``syllabus_context``   authoritative ``SYLLABUS`` chunks (learning
                       objectives). Topic-matched first, then a bounded
                       whole-notebook fallback so a sparse syllabus still
                       yields grounding. Raises ``InsufficientSources`` when
                       the notebook has no usable syllabus text at all.
``historical_context`` ``QUESTION`` chunks linked to the selected topics by
                       a **confirmed** ``QuestionTopic`` row, optionally
                       bounded to a year range, and never a ``FAILED``
                       question. Used only as exam-style examples.

Each row carries a real ``source_key`` (never synthetic) so the citation
filter downstream can prove every reference exists. Retrieval is read-only;
nothing is written here.
"""

from django.conf import settings

from ...models import DocumentChunk, Question, QuestionTopic
from ..analytics.labels import normalize_label
from .errors import InvalidRequest, InsufficientSources

# Bounded so one prompt cannot be flooded by a huge syllabus.
_MAX_TOPIC_ROWS = 8
_MAX_FALLBACK_ROWS = 4
_MAX_HISTORY_ROWS = 8
_CHAR_CAP = 4000
_DEFAULT_CONTEXT_BUDGET = 6000
_MIN_CONTEXT_BUDGET = 500


def _context_budget():
    """Total character budget across both labelled blocks."""
    try:
        budget = int(getattr(
            settings, 'GENERATION_CONTEXT_CHARS', _DEFAULT_CONTEXT_BUDGET
        ))
    except (TypeError, ValueError):
        budget = _DEFAULT_CONTEXT_BUDGET
    return max(_MIN_CONTEXT_BUDGET, budget)


def _topic_labels(topic):
    """Primary name plus curated aliases (normalised for matching)."""
    names = [topic.name] + list(topic.aliases or [])
    return [normalize_label(name) for name in names if normalize_label(name)]


def _mentions_topic(text, labels):
    if not text:
        return False
    lowered = text.lower()
    return any(label.lower() in lowered for label in labels)


def _syllabus_rows(notebook):
    """All indexed syllabus chunks for this notebook, oldest chunk first."""
    rows = DocumentChunk.objects.filter(
        notebook=notebook,
        source_type=DocumentChunk.SOURCE_SYLLABUS,
    ).order_by('chunk_index', 'id')
    return list(rows)


def syllabus_context(notebook, topic):
    """Syllabus chunks for one topic; falls back to a whole-notebook sample."""
    all_rows = _syllabus_rows(notebook)
    if not all_rows:
        raise InsufficientSources(
            'This notebook has no indexed syllabus material for that topic.'
        )

    labels = _topic_labels(topic)
    matched = [row for row in all_rows if _mentions_topic(row.text, labels)]
    chosen = matched[:_MAX_TOPIC_ROWS]

    notices = []
    if matched:
        notices.append('syllabus_topic_matched')
    else:
        # No passage literally names the topic: fall back to a small
        # whole-syllabus sample so the model still has real learning
        # objectives, but flag it so the UI can show the weaker grounding.
        chosen = all_rows[:_MAX_FALLBACK_ROWS]
        notices.append('syllabus_topic_unmatched')

    return _render(chosen), notices


def historical_context(notebook, topic, *, year_from=None, year_to=None):
    """Past-paper questions linked to the topic by a confirmed link."""
    if year_from is not None and year_to is not None:
        if year_from > year_to:
            raise InvalidRequest('year_from must not be greater than year_to.')

    qs = (
        Question.objects.filter(
            notebook=notebook,
            topic_links__topic=topic,
            topic_links__role=QuestionTopic.ROLE_PRIMARY,
            topic_links__review_status='CONFIRMED',
        )
        .exclude(extraction_status=Question.STATUS_FAILED)
        .order_by('year', 'question_number')
    )
    if year_from is not None:
        qs = qs.filter(year__gte=year_from)
    if year_to is not None:
        qs = qs.filter(year__lte=year_to)

    questions = list(qs[:_MAX_HISTORY_ROWS])
    if not questions:
        return [], ['no_historical_examples']

    # Map each question to its first indexed chunk. The chunk's own
    # ``source_key`` is authoritative (``q:{id}:c:{chunk_index}``); deriving
    # one from the database id would produce a key that does not exist.
    chunk_by_question = {}
    chunks = DocumentChunk.objects.filter(
        notebook=notebook,
        source_type=DocumentChunk.SOURCE_QUESTION,
        question_id__in=[q.id for q in questions],
    ).values_list('source_key', 'question_id', 'text')
    for source_key, question_id, text in chunks:
        chunk_by_question.setdefault(question_id, (source_key, text))

    rows = []
    for question in questions:
        found = chunk_by_question.get(question.id)
        if not found:
            continue
        source_key, text = found
        paper = question.exam_paper if question.exam_paper_id else None
        rows.append({
            'source_key': source_key,
            'source_type': DocumentChunk.SOURCE_QUESTION,
            'document_title': paper.title if paper else '',
            'question_number': question.question_number,
            'year': question.year,
            'text': (text or '')[:_CHAR_CAP],
        })
    notices = []
    if not rows:
        notices.append('no_historical_examples')
    return rows, notices


def _render(chunks):
    """Turn ``DocumentChunk`` rows into context rows with real source_keys."""
    rendered = []
    for chunk in chunks:
        metadata = chunk.metadata or {}
        rendered.append({
            'source_key': chunk.source_key,
            'source_type': chunk.source_type,
            'document_title': metadata.get('document', ''),
            'question_number': chunk.question_number,
            'year': chunk.year,
            'page_number': chunk.page_number,
            'text': (chunk.text or '')[:_CHAR_CAP],
        })
    return rendered


def _fit_budget(syllabus_rows, history_rows, budget):
    """Trim both blocks to one combined character budget.

    Syllabus text is authoritative and is allocated first; historical
    examples only receive what remains. Rows are never fabricated, only
    shortened or omitted, and at least one syllabus row is kept when the
    notebook had syllabus text.
    """
    remaining = budget
    fitted_syllabus = []
    for row in syllabus_rows:
        if remaining <= 0:
            break
        text = row.get('text') or ''
        if len(text) > remaining:
            row = {**row, 'text': text[:remaining]}
        fitted_syllabus.append(row)
        remaining -= len(row['text'])

    fitted_history = []
    for row in history_rows:
        if remaining <= 0:
            break
        text = row.get('text') or ''
        if len(text) > remaining:
            row = {**row, 'text': text[:remaining]}
        fitted_history.append(row)
        remaining -= len(row['text'])

    return fitted_syllabus, fitted_history


def build_context(notebook, topic, *, year_from=None, year_to=None):
    """Both contexts plus the notices the UI can surface."""
    syllabus_rows, syllabus_notices = syllabus_context(notebook, topic)
    history_rows, history_notices = historical_context(
        notebook, topic, year_from=year_from, year_to=year_to
    )
    syllabus_rows, history_rows = _fit_budget(
        syllabus_rows, history_rows, _context_budget()
    )
    return {
        'syllabus': syllabus_rows,
        'history': history_rows,
        'notices': syllabus_notices + history_notices,
    }
