"""Deterministic topic-label normalisation, matching and suggestion.

Every function here is pure: no database access, no LLM. The analytics layer
uses these rules for (a) turning human/model labels into the canonical form
stored on ``NotebookTopic.normalized_name`` and its ``aliases``, (b) deciding
whether a proposal resolves an existing topic, is new, or is ambiguous, and
(c) suggesting candidates for labels that do not resolve exactly. Matching is
exact on the normalised string; the suggestion path only ever *suggests* and
never silently links a question to a topic.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from predictor.services.analytics.errors import InvalidRequest

MAX_LABEL_CHARS = 200
SUGGESTION_MIN_SCORE = 0.34
MAX_SUGGESTIONS = 3

_EDGE_PUNCTUATION = " \t\"'`“”‘’,.;:!?()[]{}<>/\\|-–—*#_~&"
_STOPWORDS = frozenset({
    'a', 'an', 'and', 'are', 'at', 'by', 'for', 'from', 'in', 'is', 'of', 'on',
    'or', 'the', 'to', 'with',
})


@dataclass(frozen=True)
class LabelMatch:
    """Result of resolving a label against a normalised catalogue index."""

    normalized: str
    status: str
    topic_ids: tuple[int, ...] = ()
    suggestions: tuple[tuple[int, float], ...] = ()

    @property
    def resolved(self) -> bool:
        return self.status == 'RESOLVED'

    @property
    def ambiguous(self) -> bool:
        return self.status == 'AMBIGUOUS'


def normalize_label(label: str) -> str:
    """NFKC -> casefold -> collapse whitespace -> strip edge punctuation."""
    if not isinstance(label, str):
        return ''
    text = unicodedata.normalize('NFKC', label).casefold()
    text = ' '.join(text.split())
    text = text.strip(_EDGE_PUNCTUATION)
    return ' '.join(text.split())


def check_label(label: str, *, field_name: str = 'label') -> str:
    """Validate and normalise a label, raising ``InvalidRequest`` if unusable."""
    if not isinstance(label, str) or not label.strip():
        raise InvalidRequest(f'{field_name} must be a non-empty string.')
    if len(label) > MAX_LABEL_CHARS:
        raise InvalidRequest(
            f'{field_name} must be at most {MAX_LABEL_CHARS} characters.',
        )
    normalized = normalize_label(label)
    if not normalized:
        raise InvalidRequest(
            f'{field_name} must contain letters or digits once normalised.',
        )
    return normalized


def label_tokens(label: str) -> frozenset[str]:
    """Stopword-filtered token set of the normalised label."""
    return frozenset(
        token for token in normalize_label(label).split()
        if token and token not in _STOPWORDS
    )


def overlap_score(left: str, right: str) -> float:
    """Jaccard overlap of the two labels' token sets (0.0 if either is empty)."""
    left_tokens, right_tokens = label_tokens(left), label_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def resolve(label: str,
            index: dict[str, list[int]],
            *,
            suggestion_min: float = SUGGESTION_MIN_SCORE) -> LabelMatch:
    """Resolve ``label`` against a normalised catalogue index.

    Exact normalised matches return ``RESOLVED`` (one topic) or ``AMBIGUOUS``
    (the same label maps to several topics - a human must disambiguate).
    Anything else is ``NEW`` and carries up to ``MAX_SUGGESTIONS`` candidates
    whose token overlap reaches ``suggestion_min``; suggestions are advisory
    only and are never applied automatically.
    """
    normalized = normalize_label(label)
    if not normalized:
        return LabelMatch(normalized=normalized, status='NEW')

    hits = index.get(normalized)
    if hits:
        unique = tuple(sorted(set(hits)))
        if len(unique) == 1:
            return LabelMatch(normalized=normalized, status='RESOLVED',
                              topic_ids=unique)
        return LabelMatch(normalized=normalized, status='AMBIGUOUS',
                          topic_ids=unique,
                          suggestions=tuple((tid, 1.0) for tid in unique))

    best: dict[int, float] = {}
    for key, ids in index.items():
        score = overlap_score(normalized, key)
        if score < suggestion_min:
            continue
        for topic_id in set(ids):
            if score > best.get(topic_id, -1.0):
                best[topic_id] = score
    ranked = sorted(best.items(), key=lambda item: (-item[1], item[0]))
    return LabelMatch(
        normalized=normalized,
        status='NEW',
        suggestions=tuple(
            (topic_id, round(score, 4))
            for topic_id, score in ranked[:MAX_SUGGESTIONS]
        ),
    )


def dedupe_labels(labels: list[str]) -> list[str]:
    """Drop empty and duplicate labels, preserving first-seen order."""
    seen: set[str] = set()
    kept: list[str] = []
    for label in labels:
        normalized = normalize_label(label)
        if normalized and normalized not in seen:
            seen.add(normalized)
            kept.append(label.strip())
    return kept


def validate_proposed_topics(topics: list[str],
                             *,
                             field_name: str = 'topics') -> list[str]:
    """Validate a proposal's topic label list (bounded, deduplicated)."""
    if not isinstance(topics, list):
        raise InvalidRequest(f'{field_name} must be a list of strings.')
    if len(topics) > 10:
        raise InvalidRequest(f'{field_name} may contain at most 10 labels.')
    cleaned = [str(topic).strip() for topic in topics if str(topic).strip()]
    for topic in cleaned:
        if len(topic) > MAX_LABEL_CHARS:
            raise InvalidRequest(
                f'{field_name} entries must be at most {MAX_LABEL_CHARS} '
                'characters.',
            )
    return dedupe_labels(cleaned)
