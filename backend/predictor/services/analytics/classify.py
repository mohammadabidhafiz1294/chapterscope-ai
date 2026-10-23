"""Apply label proposals to one notebook: deterministic pass, then LLM pass.

Two independent, both-optional proposal sources:

* **Rule pass (always available, no key needed)** - a topic name or alias
  that appears as a whole word inside the question text is proposed as a
  ``RULE`` link. Matching is exact-label only (no fuzzy scoring, no synonym
  guessing), so it is reproducible from the data alone.
* **LLM pass (``use_llm=true``, needs a key)** - the proposer returns
  structured labels per question; each label is resolved against the
  notebook catalogue with ``labels.resolve``: an exact name/alias match
  becomes a link, an unknown label creates a **new topic in NEEDS_REVIEW**
  state, and an ambiguous label creates nothing and is returned as an
  unresolved suggestion with its candidates.

Every link this module creates is ``review_status=NEEDS_REVIEW`` with its
source and classifier version recorded, so nothing counts in analytics until
a human confirms it through ``POST /analytics/review/``. Rows are never
overwritten: an existing (question, topic) pair or an existing PRIMARY link
is left untouched, and rejected rows are never revived.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from django.conf import settings
from django.db import transaction

from predictor.models import NotebookTopic, QuestionTopic
from predictor.services.analytics.catalog import build_catalogue
from predictor.services.analytics.errors import InvalidRequest
from predictor.services.analytics.labels import (
    check_label,
    normalize_label,
    resolve,
)
from predictor.services.analytics.metrics import scope_questions
from predictor.services.analytics.proposer import QuestionProposal, get_proposer

logger = logging.getLogger(__name__)

RULE_VERSION = 'keyword-match/v1'
MAX_EXPLICIT_IDS = 200
_WORD_BOUNDARY = r'(?<!\w){}(?!\w)'


def _batch_limit(limit: Any) -> int:
    configured = max(1, int(getattr(settings, 'TOPIC_LLM_MAX_QUESTIONS', 20)))
    if limit in (None, ''):
        return configured
    try:
        value = int(limit)
    except (TypeError, ValueError) as exc:
        raise InvalidRequest(
            f'limit must be an integer between 1 and {configured}.',
        ) from exc
    if value < 1 or value > configured:
        raise InvalidRequest(
            f'limit must be an integer between 1 and {configured}.',
        )
    return value


def _parse_question_ids(question_ids: Any) -> list[int]:
    if question_ids in (None, ''):
        return []
    if not isinstance(question_ids, (list, tuple)):
        raise InvalidRequest('question_ids must be a list of question ids.')
    if len(question_ids) > MAX_EXPLICIT_IDS:
        raise InvalidRequest(
            f'question_ids may contain at most {MAX_EXPLICIT_IDS} ids.',
        )
    parsed: list[int] = []
    for value in question_ids:
        try:
            parsed.append(int(value))
        except (TypeError, ValueError) as exc:
            raise InvalidRequest('question_ids must be integers.') from exc
    return parsed


def _select_questions(notebook, question_ids: list[int], batch: int):
    base = (
        scope_questions(notebook)
        .exclude(raw_text='')
        .select_related('exam_paper')
        .order_by('id')
    )
    if question_ids:
        available = set(
            base.filter(id__in=question_ids).values_list('id', flat=True)
        )
        if set(question_ids) - available:
            raise InvalidRequest(
                'Some question_ids are not questions of this notebook.',
                hint='Ids outside this notebook are reported the same way as '
                     'unknown ids.',
            )
        return list(base.filter(id__in=question_ids)[:batch])

    selected = list(
        base.exclude(
            topic_links__role='PRIMARY',
            topic_links__review_status='CONFIRMED',
        )[:batch]
    )
    if len(selected) < batch:
        already = [question.id for question in selected]
        fillers = base.exclude(id__in=already)
        selected = selected + list(fillers[:batch - len(selected)])
    return selected


def _rule_proposal(question, catalogue) -> tuple[str, list[str]]:
    """Exact whole-label matches inside the question text, longest label first."""
    text = ' '.join((question.raw_text or '').split())
    if not text:
        return '', []
    matches: list[tuple[int, int, str]] = []
    for entry in catalogue.entries:
        for label in entry.labels:
            if not label:
                continue
            if re.search(
                _WORD_BOUNDARY.format(re.escape(label)), text,
                flags=re.IGNORECASE,
            ):
                matches.append(
                    (len(normalize_label(label)), entry.id, entry.name)
                )
                break
    if not matches:
        return '', []
    matches.sort(key=lambda item: (-item[0], item[1]))
    primary_id, primary_name = matches[0][1], matches[0][2]
    secondaries = [
        name for _length, topic_id, name in matches[1:] if topic_id != primary_id
    ]
    return primary_name, secondaries


def _payload_questions(questions: list) -> list[dict]:
    return [
        {
            'id': question.id,
            'year': question.exam_paper.year,
            'marks': question.marks,
            'question_type': question.question_type,
            'text': question.raw_text,
        }
        for question in questions
    ]


class _Batch:
    """Accumulates creates for one request and applies them in one transaction."""

    def __init__(self, notebook, catalogue):
        self.notebook = notebook
        self.catalogue = catalogue
        self.local_index: dict[str, list[int]] = {}
        self.topics_created: list[dict] = []
        self.links_created: list[dict] = []
        self.unresolved: list[dict] = []
        self.low_confidence: list[dict] = []
        self.types_proposed: list[dict] = []
        self.primary_by_question: dict[int, set[int]] = {}
        self.labels: dict[int, str] = {}

    def load_existing_primary(self, questions: list) -> None:
        ids = [question.id for question in questions]
        if not ids:
            return
        rows = QuestionTopic.objects.filter(
            question_id__in=ids, role='PRIMARY',
        ).values_list('question_id', 'topic_id')
        for question_id, topic_id in rows:
            self.primary_by_question.setdefault(question_id, set()).add(topic_id)

    def index(self) -> dict[str, list[int]]:
        merged = {key: list(ids) for key, ids in self.catalogue.index.items()}
        for key, ids in self.local_index.items():
            bucket = merged.setdefault(key, [])
            bucket.extend(
                topic_id for topic_id in ids if topic_id not in bucket
            )
        return merged

    def ensure_topic(self, label: str) -> int | None:
        normalized = check_label(label, field_name='topic')
        hits = self.index().get(normalized)
        if hits:
            return hits[0] if len(hits) == 1 else None
        topic = NotebookTopic.objects.create(
            notebook=self.notebook,
            name=label.strip(),
            normalized_name=normalized,
            review_status='NEEDS_REVIEW',
        )
        self.local_index.setdefault(normalized, []).append(topic.id)
        self.labels[topic.id] = topic.name
        self.topics_created.append({
            'id': topic.id,
            'name': topic.name,
            'review_status': topic.review_status,
        })
        return topic.id

    def topic_name(self, topic_id: int) -> str:
        if topic_id in self.labels:
            return self.labels[topic_id]
        entry = self.catalogue.get(topic_id)
        return entry.name if entry else str(topic_id)

    def add_link(self, question, topic_id: int, *, role: str, source: str,
                 confidence: float | None, version: str) -> bool:
        if QuestionTopic.objects.filter(
            question=question, topic_id=topic_id,
        ).exists():
            return False
        existing_primary = self.primary_by_question.setdefault(question.id, set())
        if role == 'PRIMARY':
            if existing_primary:
                role = 'SECONDARY'
            else:
                existing_primary.add(topic_id)
        link = QuestionTopic.objects.create(
            question=question,
            topic_id=topic_id,
            role=role,
            classification_source=source,
            confidence=confidence,
            classifier_version=version,
            review_status='NEEDS_REVIEW',
        )
        self.links_created.append({
            'id': link.id,
            'question_id': question.id,
            'topic_id': topic_id,
            'topic_name': self.topic_name(topic_id),
            'role': link.role,
            'classification_source': source,
            'classifier_version': link.classifier_version,
            'confidence': confidence,
            'review_status': link.review_status,
        })
        return True

    def apply_type(self, proposal: QuestionProposal, question, *,
                   threshold: float, version: str) -> None:
        if not proposal.question_type or question.question_type:
            return
        applied = (
            proposal.type_confidence is not None
            and proposal.type_confidence >= threshold
        )
        self.types_proposed.append({
            'question_id': question.id,
            'question_type': proposal.question_type,
            'confidence': proposal.type_confidence,
            'applied': applied,
        })
        if not applied:
            return
        question.question_type = proposal.question_type
        question.type_source = 'LLM'
        question.type_confidence = proposal.type_confidence
        question.type_classifier_version = version
        question.type_review_status = 'NEEDS_REVIEW'
        question.save(update_fields=[
            'question_type', 'type_source', 'type_confidence',
            'type_classifier_version', 'type_review_status',
        ])


def _resolve_label(label: str, batch: _Batch, *, question) -> int | None:
    """Resolve one proposed label to a topic id; record ambiguous/new cases."""
    match = resolve(label, batch.index())
    if match.ambiguous:
        batch.unresolved.append({
            'question_id': question.id,
            'label': label,
            'status': match.status,
            'candidates': [
                {
                    'topic_id': topic_id,
                    'name': batch.topic_name(topic_id),
                    'score': score,
                }
                for topic_id, score in match.suggestions
            ],
        })
        return None
    if match.resolved:
        return match.topic_ids[0]
    return batch.ensure_topic(label)


def _apply_llm(batch: _Batch, questions_by_id: dict[int, Any],
               proposals: list[QuestionProposal], version: str,
               threshold: float) -> None:
    for proposal in proposals:
        question = questions_by_id.get(proposal.question_id)
        if question is None:
            continue
        if (proposal.confidence < threshold
                and (proposal.primary or proposal.secondary)):
            batch.low_confidence.append({
                'question_id': question.id,
                'labels': list(proposal.topics),
                'confidence': proposal.confidence,
            })
        else:
            if proposal.primary:
                topic_id = _resolve_label(
                    proposal.primary, batch, question=question,
                )
                if topic_id is not None:
                    batch.add_link(
                        question, topic_id, role='PRIMARY', source='LLM',
                        confidence=proposal.confidence, version=version,
                    )
            for label in proposal.secondary:
                secondary_id = _resolve_label(label, batch, question=question)
                if secondary_id is not None:
                    batch.add_link(
                        question, secondary_id, role='SECONDARY', source='LLM',
                        confidence=proposal.confidence, version=version,
                    )
        batch.apply_type(
            proposal, question, threshold=threshold, version=version,
        )


def propose_classifications(notebook, *, question_ids: Any = None,
                            limit: Any = None, use_llm: bool = True,
                            proposer: Any = None) -> dict:
    """Create review-queue rows and report exactly what was created.

    Raises before writing anything when an explicitly requested LLM pass is
    unavailable (``LLMUnavailable``, 503) or answers with an unusable shape
    (``LLMInvalidResponse``, 502), so a failed model call never leaves a
    half-applied batch behind.
    """
    batch_size = _batch_limit(limit)
    ids = _parse_question_ids(question_ids)
    threshold = float(getattr(settings, 'TOPIC_REVIEW_MIN_CONFIDENCE', 0.75))
    catalogue = build_catalogue(notebook)
    questions = _select_questions(notebook, ids, batch_size)

    notices: list[str] = []
    proposals: list[QuestionProposal] = []
    version = RULE_VERSION
    llm_invoked = False
    if not use_llm:
        notices.append('llm_disabled')
    if not questions:
        notices.append('no_questions_to_label')

    with transaction.atomic():
        batch_obj = _Batch(notebook, catalogue)
        batch_obj.load_existing_primary(questions)

        if use_llm and questions:
            active = proposer or get_proposer()
            llm_invoked = True
            version = active.version
            proposals = active.propose(
                _payload_questions(questions), catalogue.names,
            )

        for question in questions:
            primary, secondaries = _rule_proposal(question, catalogue)
            if not primary:
                continue
            topic_id = batch_obj.ensure_topic(primary)
            if topic_id is None:
                continue
            batch_obj.add_link(
                question, topic_id, role='PRIMARY', source='RULE',
                confidence=None, version=RULE_VERSION,
            )
            for label in secondaries:
                secondary_id = batch_obj.ensure_topic(label)
                if secondary_id is None:
                    continue
                batch_obj.add_link(
                    question, secondary_id, role='SECONDARY', source='RULE',
                    confidence=None, version=RULE_VERSION,
                )

        if proposals:
            _apply_llm(
                batch_obj,
                {question.id: question for question in questions},
                proposals,
                version,
                threshold,
            )

    if not batch_obj.links_created and not batch_obj.topics_created:
        notices.append('nothing_applied')
    return {
        'notebook_id': notebook.id,
        'used_llm': llm_invoked,
        'model': version,
        'requested': len(questions),
        'threshold': threshold,
        'links_created': batch_obj.links_created,
        'topics_created': batch_obj.topics_created,
        'types_proposed': batch_obj.types_proposed,
        'unresolved': batch_obj.unresolved,
        'low_confidence': batch_obj.low_confidence,
        'notices': notices,
    }
