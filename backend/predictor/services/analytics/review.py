"""Human review actions: confirm/reject labels, manual topic assignment.

This is the only place where classifier output becomes counted data. Every
action is applied to rows that must already belong to the caller's notebook
(an unknown id and a foreign id are indistinguishable, both 400), and every
action is idempotent: confirming an already confirmed link simply writes the
same value again.

Rules enforced here:

* A question can own at most one ``PRIMARY`` row (database constraint), so
  assigning a new primary demotes any previous primary row to a rejected
  ``SECONDARY`` - history is kept, never deleted, and rejected rows are
  never silently revived by a later proposal.
* Rejecting a topic is refused while it still has confirmed links, so the
  review queue cannot orphan counted data.
* Type labels can only be confirmed or rejected while they are pending
  (``type_review_status=NEEDS_REVIEW``); rejection clears the proposed type
  and its provenance.

Renaming a topic or editing its aliases is ordinary CRUD and goes through
``NotebookTopicSerializer`` (400 field errors on label collisions), not
through this module.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction

from predictor.models import NotebookTopic, QuestionTopic
from predictor.services.analytics.errors import InvalidRequest
from predictor.services.analytics.metrics import scope_questions

ACTIONS = ('confirm', 'reject')


def _as_int(value: Any, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise InvalidRequest(f'{field} must be an integer id.') from exc


def _items(payload: Any, name: str, key: str) -> list[dict]:
    if payload in (None, ''):
        return []
    if not isinstance(payload, (list, tuple)):
        raise InvalidRequest(f'{name} must be a list of objects.')
    items: list[dict] = []
    for item in payload:
        if not isinstance(item, dict) or key not in item or 'action' not in item:
            raise InvalidRequest(
                f'Each {name} item needs "{key}" and "action".',
            )
        action = str(item.get('action', '')).strip().lower()
        if action not in ACTIONS:
            raise InvalidRequest(
                f'"{action}" is not a valid action; use confirm or reject.',
            )
        items.append(dict(item, action=action))
    return items


def pending_queue(notebook, *, limit: int = 100) -> dict:
    """Read-only snapshot of this notebook's review queue for the UI.

    The proposals response only carries the rows it just created, so the
    frontend (and anyone returning to a half-reviewed batch) needs a way to
    list what is still waiting: pending links, pending topics and pending
    type labels, each capped at ``limit`` rows, notebook-scoped and ordered
    deterministically.
    """
    if limit in (None, ''):
        cap = 100
    else:
        try:
            cap = max(1, min(int(limit), 500))
        except (TypeError, ValueError) as exc:
            raise InvalidRequest('limit must be an integer.') from exc

    links = [
        {
            'id': row.id,
            'question_id': row.question_id,
            'question_number': row.question.question_number,
            'text': (row.question.raw_text or '')[:140],
            'topic_id': row.topic_id,
            'topic_name': row.topic.name,
            'role': row.role,
            'confidence': row.confidence,
            'classification_source': row.classification_source,
            'review_status': row.review_status,
        }
        for row in QuestionTopic.objects.filter(
            question__exam_paper__notebook=notebook,
            topic__notebook=notebook,
            review_status='NEEDS_REVIEW',
        ).select_related('question', 'topic').order_by('id')[:cap]
    ]
    topics = [
        {
            'id': topic.id,
            'name': topic.name,
            'aliases': list(topic.aliases or []),
            'review_status': topic.review_status,
        }
        for topic in NotebookTopic.objects.filter(
            notebook=notebook, review_status='NEEDS_REVIEW',
        ).order_by('normalized_name', 'id')[:cap]
    ]
    types = [
        {
            'question_id': question.id,
            'question_number': question.question_number,
            'text': (question.raw_text or '')[:140],
            'question_type': question.question_type,
            'type_confidence': question.type_confidence,
            'type_source': question.type_source,
        }
        for question in scope_questions(notebook).filter(
            type_review_status='NEEDS_REVIEW',
        ).order_by('id')[:cap]
    ]
    return {'links': links, 'topics': topics, 'types': types}


def apply_review(notebook, *, links: Any = None, topics: Any = None,
                 types: Any = None) -> dict:
    """Apply batch review actions for this notebook's queue."""
    link_items = _items(links, 'links', 'id')
    topic_items = _items(topics, 'topics', 'id')
    type_items = _items(types, 'types', 'question_id')
    if not (link_items or topic_items or type_items):
        raise InvalidRequest(
            'Provide at least one of links, topics or types to review.',
        )

    results: dict[str, Any] = {'links': [], 'topics': [], 'types': []}
    with transaction.atomic():
        if link_items:
            wanted = {_as_int(item['id'], 'id') for item in link_items}
            rows = {
                row.id: row
                for row in QuestionTopic.objects.filter(
                    id__in=wanted,
                    question__exam_paper__notebook=notebook,
                    topic__notebook=notebook,
                )
            }
            if set(rows) != wanted:
                raise InvalidRequest('Some link ids are not from this notebook.')
            for item in link_items:
                row = rows[_as_int(item['id'], 'id')]
                status = 'CONFIRMED' if item['action'] == 'confirm' else 'REJECTED'
                if row.review_status != status:
                    row.review_status = status
                    row.save(update_fields=['review_status'])
                results['links'].append({'id': row.id, 'status': status})

        if topic_items:
            wanted = {_as_int(item['id'], 'id') for item in topic_items}
            rows = {
                topic.id: topic
                for topic in NotebookTopic.objects.filter(
                    id__in=wanted, notebook=notebook,
                )
            }
            if set(rows) != wanted:
                raise InvalidRequest('Some topic ids are not from this notebook.')
            for item in topic_items:
                topic = rows[_as_int(item['id'], 'id')]
                if item['action'] == 'reject' and QuestionTopic.objects.filter(
                    topic=topic, review_status='CONFIRMED',
                ).exists():
                    raise InvalidRequest(
                        f'Topic "{topic.name}" still has confirmed links; '
                        'reject those links first.',
                    )
                status = (
                    'CONFIRMED' if item['action'] == 'confirm' else 'NEEDS_REVIEW'
                )
                if topic.review_status != status:
                    topic.review_status = status
                    topic.save(update_fields=['review_status', 'updated_at'])
                results['topics'].append({'id': topic.id, 'status': status})

        if type_items:
            wanted = {_as_int(item['question_id'], 'question_id')
                      for item in type_items}
            questions = {
                question.id: question
                for question in scope_questions(notebook).filter(id__in=wanted)
            }
            if set(questions) != wanted:
                raise InvalidRequest(
                    'Some question ids are not from this notebook.',
                )
            for item in type_items:
                question = questions[_as_int(item['question_id'], 'question_id')]
                if question.type_review_status != 'NEEDS_REVIEW':
                    raise InvalidRequest(
                        f'Question {question.id} has no pending type label.',
                    )
                if item['action'] == 'confirm':
                    question.type_review_status = 'CONFIRMED'
                    question.save(update_fields=['type_review_status'])
                    results['types'].append({
                        'question_id': question.id,
                        'question_type': question.question_type,
                        'status': 'CONFIRMED',
                    })
                else:
                    question.question_type = ''
                    question.type_source = ''
                    question.type_confidence = None
                    question.type_classifier_version = ''
                    question.type_review_status = ''
                    question.save(update_fields=[
                        'question_type', 'type_source', 'type_confidence',
                        'type_classifier_version', 'type_review_status',
                    ])
                    results['types'].append({
                        'question_id': question.id,
                        'question_type': '',
                        'status': 'REJECTED',
                    })
    return results


def assign_link(notebook, *, question_id: Any, topic_id: Any,
                role: Any = 'PRIMARY', confidence: Any = None) -> dict:
    """Manually link one of this notebook's questions to one of its topics."""
    question = scope_questions(notebook).filter(
        pk=_as_int(question_id, 'question_id'),
    ).first()
    if question is None:
        raise InvalidRequest('question_id is not a question of this notebook.')
    topic = NotebookTopic.objects.filter(
        pk=_as_int(topic_id, 'topic_id'), notebook=notebook,
    ).first()
    if topic is None:
        raise InvalidRequest('topic_id is not a topic of this notebook.')
    role = str(role or 'PRIMARY').upper()
    if role not in ('PRIMARY', 'SECONDARY'):
        raise InvalidRequest("role must be 'PRIMARY' or 'SECONDARY'.")
    if confidence not in (None, ''):
        try:
            confidence = float(confidence)
        except (TypeError, ValueError) as exc:
            raise InvalidRequest('confidence must be between 0 and 1.') from exc
        if not 0.0 <= confidence <= 1.0:
            raise InvalidRequest('confidence must be between 0 and 1.')
    else:
        confidence = None

    with transaction.atomic():
        existing = QuestionTopic.objects.filter(
            question=question, topic=topic,
        ).first()
        if role == 'PRIMARY':
            others = QuestionTopic.objects.filter(
                question=question, role='PRIMARY',
            ).exclude(topic=topic)
            for row in others:
                row.role = 'SECONDARY'
                row.review_status = 'REJECTED'
                row.save(update_fields=['role', 'review_status'])
        if existing is not None:
            existing.role = role
            existing.review_status = 'CONFIRMED'
            existing.classification_source = 'MANUAL'
            existing.confidence = confidence
            existing.classifier_version = ''
            existing.save(update_fields=[
                'role', 'review_status', 'classification_source',
                'confidence', 'classifier_version',
            ])
            link, created = existing, False
        else:
            link = QuestionTopic.objects.create(
                question=question,
                topic=topic,
                role=role,
                classification_source='MANUAL',
                confidence=confidence,
                classifier_version='',
                review_status='CONFIRMED',
            )
            created = True
    return {
        'id': link.id,
        'question_id': question.id,
        'topic_id': topic.id,
        'topic_name': topic.name,
        'role': link.role,
        'classification_source': link.classification_source,
        'confidence': link.confidence,
        'review_status': link.review_status,
        'created': created,
    }
