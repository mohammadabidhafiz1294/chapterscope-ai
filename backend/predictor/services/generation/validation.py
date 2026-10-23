"""Server-side validation of one model-parsed question (Phase 7).

Every displayed fact and source reference is rebuilt from the retrieved
context rows, never trusted from the model. A question is never dropped for
failing a check; it is *flagged* (``needs_review``) with machine-readable
reason codes so a human can decide. This keeps a bad generation attempt from
silently vanishing while making sure nothing unverified is presented as
correct.

Checks, in order:

``schema_valid``            already enforced by Pydantic (``extra='forbid'``).
``grounding``               at least one cited ``source_key`` must exist in
                            the retrieved context; fabricated keys dropped.
``syllabus_alignment``      must cite at least one *syllabus* source.
``marks_rubric_coherence``  rubric present, items sum to ``marks``.
``duplicate``               near-identical to a past question or another
                            generated question in the same notebook.
``numeric``                 only when ``question_type='numerical'`` and a
                            ``numeric_problem`` is supplied; runs math_checks.
``confidence``              below the configured floor -> needs_review.

The result carries the server-built ``source_refs`` plus the reason codes
that drove the status.
"""

import re

from django.conf import settings

from ...models import GeneratedQuestion
from . import math_checks

_NUMBER_RE = re.compile(
    r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?'
)


def _int_setting(name, default):
    try:
        return int(getattr(settings, name, default))
    except (TypeError, ValueError):
        return default


def _float_setting(name, default):
    try:
        return float(getattr(settings, name, default))
    except (TypeError, ValueError):
        return default


def normalize_text(text):
    """Lowercase + collapse whitespace + strip punctuation for comparison."""
    cleaned = []
    for char in (text or '').lower():
        cleaned.append(char if char.isalnum() else ' ')
    return ' '.join(''.join(cleaned).split())


def _token_set(text):
    return set(normalize_text(text).split())


def similarity(a, b):
    """Jaccard token overlap in [0, 1]; 1.0 when both are empty/equal."""
    left, right = _token_set(a), _token_set(b)
    if not left or not right:
        return 1.0 if left == right else 0.0
    return len(left & right) / len(left | right)


def _existing_entries(existing_texts):
    """Yield ``(text, kind)`` from strings, pairs or ``{"text", "kind"}``."""
    for entry in existing_texts or []:
        if isinstance(entry, dict):
            yield (entry.get('text') or ''), entry.get('kind') or 'past'
        elif isinstance(entry, (tuple, list)) and len(entry) == 2:
            yield (entry[0] or ''), (entry[1] or 'past')
        else:
            yield (entry or ''), 'past'


def find_duplicate(text, existing_texts):
    """Return the best-matching existing text above threshold, or ``None``."""
    threshold = _float_setting('GENERATION_DUPLICATE_THRESHOLD', 0.85)
    best, best_score, best_kind = None, 0.0, 'past'
    for other, kind in _existing_entries(existing_texts):
        score = similarity(text, other)
        if score > best_score:
            best, best_score, best_kind = other, score, kind
    if best is not None and best_score >= threshold:
        return {
            'score': round(best_score, 4),
            'matched': best[:200],
            'kind': best_kind,
        }
    return None


def build_source_refs(cited_keys, context_rows):
    """Server-built citation payloads for the cited keys that really exist.

    Display fields are taken from the context row (never the model). A key
    the model invented is silently dropped here; the caller detects the
    difference and flags the question.
    """
    by_key = {row['source_key']: row for row in context_rows}
    refs = []
    seen = set()
    cap = _int_setting('GENERATION_MAX_SOURCE_REFS', 8)
    for key in cited_keys:
        key = (key or '').strip()
        if not key or key in seen or key not in by_key:
            continue
        seen.add(key)
        row = by_key[key]
        refs.append({
            'source_key': row['source_key'],
            'source_type': row.get('source_type', ''),
            'document_title': row.get('document_title', ''),
            'question_number': row.get('question_number', ''),
            'year': row.get('year'),
            'page_number': row.get('page_number'),
            'quote': (row.get('text') or '')[:300],
        })
        if len(refs) >= max(1, cap):
            break
    return refs


def _rubric_ok(marks, rubric):
    """Rubric present, non-empty, and item marks sum to the question marks."""
    if not rubric:
        return False
    total = 0.0
    for item in rubric:
        try:
            total += float(item.get('marks', 0))
        except (TypeError, ValueError):
            return False
    return abs(total - float(marks)) <= 1e-6


def _numeric_tolerance():
    return abs(_float_setting('GENERATION_NUMERIC_TOLERANCE', 1e-6))


def _close_enough(value, expected):
    tolerance = _numeric_tolerance()
    return abs(value - expected) <= max(tolerance, tolerance * abs(expected))


def answer_matches_number(answer, expected):
    """Check the displayed answer against a recomputed numeric result.

    Returns ``True``/``False`` when a number can be found, ``None`` when the
    answer contains no usable number. The whole answer is tried as a safe
    SymPy expression first (so ``1/2`` and ``2*3`` work), then the first
    numeric tokens are compared; common unit suffixes (``2 m/s``) and
    percentages (``50%``) are tolerated. This never evaluates arbitrary code
    and never trusts the model's own ``numeric_problem.result`` alone.
    """
    if expected is None:
        return None
    text = str(answer or '').strip()
    if not text:
        return None

    try:
        value = float(math_checks.safe_sympify(text))
    except (math_checks.ParseRejected, TypeError, ValueError, OverflowError):
        value = None
    if value is not None:
        return _close_enough(value, expected)

    numbers = []
    for token in _NUMBER_RE.findall(text):
        try:
            numbers.append(float(token))
        except ValueError:
            continue
    if not numbers:
        return None
    if any(_close_enough(number, expected) for number in numbers):
        return True
    if '%' in text and any(
        _close_enough(number / 100.0, expected) for number in numbers
    ):
        return True
    return False


def validate_question(
    item,
    context_rows,
    existing_texts,
    *,
    question_type=None,
    syllabus_topic_unmatched=False,
    requested_marks=None,
):
    """Validate one parsed question against the context and the notebook.

    ``item`` is a dict already shaped like ``GeneratedQuestionSchema``.
    ``context_rows`` is the flat list of syllabus + history context rows.
    ``existing_texts`` are the notebook's past/generated question texts (for
    duplicate detection; entries may be strings or ``(text, kind)`` pairs).
    ``syllabus_topic_unmatched`` flags weaker grounding when no syllabus
    passage named the topic. ``requested_marks`` is the caller's target mark
    value, when supplied. Returns ``(status, source_refs, report,
    numeric_report)``.
    """
    report = []
    text = item.get('prompt') or ''
    cited_keys = list(item.get('source_keys') or [])

    # 1) Grounding: drop fabricated keys, then require at least one survivor.
    source_refs = build_source_refs(cited_keys, context_rows)
    valid_keys = {ref['source_key'] for ref in source_refs}
    fabricated = [
        key for key in cited_keys
        if (key or '').strip() and key.strip() not in valid_keys
    ]
    if fabricated:
        report.append('fabricated_source_dropped')
    if not source_refs:
        report.append('no_valid_sources')

    # 2) Syllabus alignment: at least one cited source must be a syllabus row,
    #    and the syllabus block must actually be topic-matched (not fallback).
    if source_refs:
        if not any(ref['source_type'] == 'SYLLABUS' for ref in source_refs):
            report.append('no_syllabus_citation')
        if syllabus_topic_unmatched:
            report.append('syllabus_topic_unmatched')

    # 3) Marks / rubric coherence.
    marks = item.get('marks')
    rubric = item.get('marking_rubric') or []
    if not _rubric_ok(marks, rubric):
        report.append('rubric_marks_mismatch')
    if requested_marks is not None and marks != requested_marks:
        report.append('requested_marks_mismatch')

    # 4) Duplicate detection against the notebook's past and generated work.
    duplicate = find_duplicate(text, existing_texts)
    if duplicate is not None:
        if duplicate.get('kind') == 'generated':
            report.append('duplicate_of_generated_question')
        else:
            report.append('duplicate_of_existing_question')

    # 5) Choice coherence: a multiple-choice question needs real options.
    if question_type == 'multiple_choice':
        options = item.get('options') or []
        if len(options) < 2:
            report.append('missing_options')

    # 6) Numerical check (only for supported, supplied problems). The
    #    recomputed result must also agree with the answer shown to a user.
    numeric_report = {}
    if question_type == 'numerical':
        problem = item.get('numeric_problem')
        if not problem:
            report.append('numeric_check_missing')
        else:
            numeric_report = math_checks.verify_numeric(problem)
            status = numeric_report.get('status')
            if status != 'MATCH':
                report.append('numeric_' + str(status).lower())
            else:
                answer_check = answer_matches_number(
                    item.get('answer'), numeric_report.get('expected')
                )
                if answer_check is None:
                    report.append('numeric_answer_unparsable')
                elif not answer_check:
                    report.append('numeric_answer_mismatch')

    # 6) Confidence floor.
    confidence = item.get('answer_confidence')
    if confidence is not None:
        floor = _float_setting('GENERATION_MIN_CONFIDENCE', 0.6)
        try:
            if float(confidence) < floor:
                report.append('low_confidence')
        except (TypeError, ValueError):
            report.append('low_confidence')

    status = (
        GeneratedQuestion.VALIDATION_VALIDATED
        if not report
        else GeneratedQuestion.VALIDATION_NEEDS_REVIEW
    )
    return status, source_refs, report, numeric_report
