"""Rule-based, offset-aware question parser (Phase 3).

Parses the reconstructed document text into individual questions and
subparts, tracking char offsets so each question can be mapped back to its
source page/chunk. Subparts stay linked to their parent via ``parent_number``.

Numbering supported:
- Top level: ``1.`` ``1)`` ``Q1`` ``Question 1`` ``Q2)``
- Subparts: ``(a)`` ``(i)`` ``2(a)`` ``2.1``

Bare ``a)``-style markers are NOT treated as subparts at line start (they are
ambiguous with multiple-choice options); options are extracted separately.
Only one level of nesting is parsed. Tables, formulas, units and figure
references are never stripped; their presence raises warnings.

Uses the existing ``QuestionSegmenter.analyze_segment`` for type / marks /
difficulty enrichment so classification logic is not duplicated.
"""

import logging
import re
import unicodedata
from typing import List, Tuple

from ..question_segmenter import QuestionSegment, QuestionSegmenter
from .text import _content_warnings
from .types import (
    QMETHOD_RULE,
    ExtractedQuestion,
)

logger = logging.getLogger(__name__)

# Top-level: "1." "1)" "Q1." "Question 2." "Q3)"
_TOP_RE = re.compile(
    r"^(?:Q(?:uestion)?\s+)?(\d{1,3})\s*[.)]\s+", re.MULTILINE
)
# Subpart with explicit parent: "2(a)" "2(ii)"
_SUB_NUMPAREN_RE = re.compile(
    r"^(\d{1,3})\(([A-Za-z]{1,4})\)\s*", re.MULTILINE
)
# Subpart "2.1" "2.12"
_SUB_NUMDOT_RE = re.compile(r"^(\d{1,3})\.(\d{1,3})\s+", re.MULTILINE)
# Subpart "(a)" "(i)" "(iv)"
_SUB_PAREN_RE = re.compile(r"^\(([A-Za-z]{1,4})\)\s*", re.MULTILINE)

_ROMAN_RE = re.compile(r"^[ivxl]+$", re.IGNORECASE)
# MCQ option lines: "a)" "B)" "c." "D."
_OPTION_RE = re.compile(r"^([a-dA-D])[.)]\s+\S", re.MULTILINE)

# Confidence heuristics.
_CONF_TOP = 0.9
_CONF_SUB = 0.75
_CONF_LOW = 0.5

# Map QuestionSegmenter type labels to Question.TYPE_CHOICES values.
_TYPE_MAP = {
    "multiple_choice": "multiple_choice",
    "true_false": "true_false",
    "short_answer": "short_answer",
    "essay": "essay",
    "calculation": "numerical",
    "unknown": "other",
}


def normalize_text(text: str) -> str:
    """Clean a raw span without discarding meaning.

    Normalizes newlines and collapses whitespace, but preserves symbols,
    units, formulas and figure references. NFC (not NFKC) so superscripts
    and special characters survive.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _is_sub_marker(text: str) -> bool:
    """Whether a marker string is a Roman-numeral or letter subpart label."""
    return bool(_ROMAN_RE.match(text)) or len(text) <= 2


def _extract_options(text: str) -> List[str]:
    """Extract multiple-choice options if the span looks like an MCQ."""
    matches = list(_OPTION_RE.finditer(text))
    if len(matches) < 3:
        return []
    return [m.group(0).strip() for m in matches]


def _scan_spans(text: str) -> List[Tuple[int, str, str, int]]:
    """Find all question/subpart markers with offsets.

    Returns a list of ``(start, question_number, parent_number, kind)``
    where kind is 0 for top-level and 1 for subpart, sorted by offset.
    Overlapping markers (e.g. a top-level match that also covers a subpart
    marker) are de-duplicated by keeping the earliest start per position.
    """
    found: List[Tuple[int, str, str, int]] = []

    for m in _TOP_RE.finditer(text):
        found.append((m.start(), m.group(1), "", 0))
    for m in _SUB_NUMPAREN_RE.finditer(text):
        parent, child = m.group(1), m.group(2)
        if _is_sub_marker(child):
            found.append((m.start(), child, parent, 1))
    for m in _SUB_NUMDOT_RE.finditer(text):
        parent, child = m.group(1), m.group(2)
        found.append((m.start(), child, parent, 1))
    for m in _SUB_PAREN_RE.finditer(text):
        label = m.group(1)
        if _is_sub_marker(label):
            found.append((m.start(), label, "", 1))

    # Sort by offset; drop any subpart that starts at the same offset as a
    # top-level match (the top-level regex already consumed that line).
    found.sort(key=lambda item: item[0])
    deduped: List[Tuple[int, str, str, int]] = []
    seen_starts = set()
    for start, number, parent, kind in found:
        if start in seen_starts:
            continue
        seen_starts.add(start)
        deduped.append((start, number, parent, kind))
    return deduped


def parse_questions(full_text: str) -> List[ExtractedQuestion]:
    """Parse questions and subparts out of reconstructed document text.

    Returns a list of ``ExtractedQuestion`` sorted by source offset. Each
    carries raw text, normalized text, offsets, marks / type / difficulty
    (via the shared segmenter) and content warnings. Page / chunk resolution
    is done later by the processor using ``resolve_location``.
    """
    if not full_text or not full_text.strip():
        return []

    spans = _scan_spans(full_text)
    if not spans:
        return []

    segmenter = QuestionSegmenter()
    questions: List[ExtractedQuestion] = []
    current_top = ""  # most recent top-level number, for parentless subparts

    for idx, (start, number, parent, kind) in enumerate(spans):
        end = spans[idx + 1][0] if idx + 1 < len(spans) else len(full_text)
        raw_span = full_text[start:end]
        # Trim trailing blank lines but keep the printed content.
        raw_span = raw_span.rstrip()
        if not raw_span.strip():
            continue

        if kind == 0:
            current_top = number
        elif not parent:
            parent = current_top

        # Separate the marker from the body for enrichment.
        body = _strip_marker(raw_span)
        normalized = normalize_text(body)

        warnings = _content_warnings(raw_span)
        confidence = _CONF_SUB if kind == 1 else _CONF_TOP

        segment = QuestionSegment(
            question_number=0,  # placeholder; enrichment ignores it
            question_text=body,
            question_type="unknown",
            options=[],
        )
        enriched = segmenter.analyze_segment(segment)

        options: List[str] = []
        if kind == 0:
            options = _extract_options(raw_span)

        qtype = _TYPE_MAP.get(enriched.question_type, "other")
        if options:
            qtype = "multiple_choice"

        # A question that carries formulas but was OCR-derived is flagged for
        # review; formula warnings alone do not force review for text PDFs.
        questions.append(
            ExtractedQuestion(
                question_number=number,
                parent_number=parent,
                raw_text=raw_span,
                normalized_text=normalized,
                char_start=start,
                char_end=end,
                marks=enriched.marks,
                question_type=qtype,
                difficulty=enriched.estimated_difficulty or "medium",
                options=options,
                confidence=confidence,
                method=QMETHOD_RULE,
                warnings=warnings,
            )
        )

    return questions


def _strip_marker(raw_span: str) -> str:
    """Remove the leading numbering marker from a raw span."""
    for regex in (
        _TOP_RE,
        _SUB_NUMPAREN_RE,
        _SUB_NUMDOT_RE,
        _SUB_PAREN_RE,
    ):
        match = regex.match(raw_span)
        if match:
            return raw_span[match.end():]
    return raw_span


def apply_ocr_confidence(
    questions: List[ExtractedQuestion],
    ocr_confidences: dict,
    review_threshold: float,
    ocr_min_confidence: float,
) -> List[ExtractedQuestion]:
    """Blend OCR page confidence into question confidence and flag review.

    ``ocr_confidences`` maps page_number -> average OCR confidence (or None).
    A question whose combined confidence falls below ``review_threshold``,
    or that carries a formula warning while OCR-derived, is marked for
    manual review via a warning flag (the processor converts this to the
    NEEDS_REVIEW status).
    """
    for question in questions:
        page_conf = ocr_confidences.get(question.page_number)
        if page_conf is not None:
            question.confidence = min(question.confidence, page_conf)
            if question.confidence < ocr_min_confidence:
                if "ocr_low_confidence" not in question.warnings:
                    question.warnings.append("ocr_low_confidence")
        elif question.page_number in ocr_confidences:
            # OCR ran but produced no confidence signal.
            question.confidence = min(question.confidence, ocr_min_confidence)
            if "ocr_low_confidence" not in question.warnings:
                question.warnings.append("ocr_low_confidence")

        if question.method == "ocr" and "formula_detected" in question.warnings:
            if "ocr_math_review" not in question.warnings:
                question.warnings.append("ocr_math_review")

        if question.confidence < review_threshold:
            if "low_confidence" not in question.warnings:
                question.warnings.append("low_confidence")
    return questions
