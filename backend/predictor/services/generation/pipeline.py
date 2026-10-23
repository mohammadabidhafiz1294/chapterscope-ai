"""The ordered Phase 7 generation turn.

``generate`` is the single entry point. Its order is deliberate and matches
the chat pipeline's discipline: validate the caller's request *before* any
write, resolve the model (503 before any write if disabled/unconfigured),
persist a ``GenerationRequest`` row, gather the two labelled contexts, ask
the model for new questions under a strict JSON contract, validate and store
each one, then finalize the request as COMPLETED / PARTIAL / FAILED.

The LLM only ever *drafts* new questions. Every displayed fact and every
source reference is rebuilt server-side from ORM rows in
:mod:`predictor.services.generation.validation`; a model that invents a
``source_key`` has it dropped, and a question left with no valid grounding is
marked ``needs_review`` rather than silently shown as correct.

``model`` and ``context_fn`` are injectable for tests, so no test ever calls
a real provider.
"""

import json
import logging
import time

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from pydantic import ValidationError

from ...models import GeneratedQuestion, GenerationRequest, NotebookTopic, Question
from . import context as context_module
from . import model as model_module
from . import prompts, validation
from .errors import (
    GenerationError,
    InsufficientSources,
    InvalidRequest,
    LLMInvalidResponse,
    TopicNotFound,
)
from .schema import GenerationEnvelope

logger = logging.getLogger(__name__)

GENERATION_VERSION = 'phase7-generation-v1'
VALID_TYPE_VALUES = frozenset(
    value for value, _label in Question.TYPE_CHOICES if value
)
VALID_DIFFICULTY_VALUES = frozenset(
    value for value, _label in Question.DIFFICULTY_CHOICES if value
)


def _int_setting(name, default):
    try:
        return int(getattr(settings, name, default))
    except (TypeError, ValueError):
        return default


def validate_request(params):
    """Normalize and range-check the caller's request before any write."""
    topic_id = params.get('topic_id')
    if not topic_id:
        raise InvalidRequest('A topic_id is required to generate questions.')
    try:
        topic_id = int(topic_id)
    except (TypeError, ValueError):
        raise InvalidRequest('topic_id must be an integer.')

    count = params.get('count', 5)
    try:
        count = int(count)
    except (TypeError, ValueError):
        raise InvalidRequest('count must be an integer.')
    cap = _int_setting('GENERATION_MAX_QUESTIONS', 20)
    if count < 1 or count > cap:
        raise InvalidRequest(f'count must be between 1 and {cap}.')

    question_types = params.get('question_types') or []
    if isinstance(question_types, str):
        question_types = [question_types]
    bad_types = [
        t for t in question_types if t not in VALID_TYPE_VALUES
    ]
    if bad_types:
        raise InvalidRequest(
            'Unknown question_types: ' + ', '.join(sorted(bad_types))
        )

    difficulty = params.get('difficulty', '')
    if difficulty and difficulty not in VALID_DIFFICULTY_VALUES:
        raise InvalidRequest('Unknown difficulty value.')

    marks = params.get('marks')
    if marks is not None:
        try:
            marks = int(marks)
        except (TypeError, ValueError):
            raise InvalidRequest('marks must be an integer.')
        if marks < 1 or marks > 200:
            raise InvalidRequest('marks must be between 1 and 200.')

    year_from = params.get('year_from')
    year_to = params.get('year_to')
    for label, value in (('year_from', year_from), ('year_to', year_to)):
        if value is not None:
            try:
                value = int(value)
            except (TypeError, ValueError):
                raise InvalidRequest(f'{label} must be an integer.')
            if label == 'year_from':
                year_from = value
            else:
                year_to = value
    if year_from is not None and year_to is not None and year_from > year_to:
        raise InvalidRequest('year_from must not be greater than year_to.')

    language = (params.get('language') or 'en').strip() or 'en'
    if len(language) > 20:
        raise InvalidRequest('language must be at most 20 characters.')

    include_answers = params.get('include_answers', True)
    if not isinstance(include_answers, bool):
        include_answers = bool(include_answers)

    return {
        'topic_id': topic_id,
        'count': count,
        'question_types': list(question_types),
        'difficulty': difficulty,
        'marks': marks,
        'language': language,
        'include_answers': include_answers,
        'year_from': year_from,
        'year_to': year_to,
    }


def _resolve_topic(notebook, topic_id):
    topic = NotebookTopic.objects.filter(pk=topic_id, notebook=notebook).first()
    if topic is None:
        raise TopicNotFound(
            'That topic does not belong to this notebook.',
            hint='Pick a topic from this notebook\'s topic list.',
        )
    return topic


def parse_answer(raw):
    """Strictly decode the model's JSON into a ``GenerationEnvelope``."""
    text = (raw or '').strip()
    if not text:
        raise LLMInvalidResponse('The model returned an empty response.')
    if text.startswith('```'):
        lines = text.splitlines()
        if lines and lines[0].startswith('```'):
            lines = lines[1:]
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        text = '\n'.join(lines).strip()
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise LLMInvalidResponse(
            'The model response was not valid JSON.'
        ) from exc
    try:
        return GenerationEnvelope.model_validate(data)
    except ValidationError as exc:
        raise LLMInvalidResponse(
            'The model response did not match the answer schema.'
        ) from exc


def generate(notebook, user, params, *, model=None, context_fn=None):
    """Generate and persist practice questions for one notebook topic.

    ``model`` and ``context_fn`` are injectable for tests. ``context_fn`` has
    the same signature as :func:`context.build_context`. Returns the payload
    describing the stored request and its questions.
    """
    started = time.monotonic()
    normalized = validate_request(params)

    # Resolve the topic before touching the model: an unknown/foreign topic is
    # a 404 even when generation happens to be disabled on this deployment.
    topic = _resolve_topic(notebook, normalized['topic_id'])
    chat_model = model if model is not None else model_module.get_generation_model()
    ctx_fn = context_fn if context_fn is not None else context_module.build_context

    request = GenerationRequest.objects.create(
        notebook=notebook,
        creator=user,
        topic=topic,
        topic_ids=[topic.id],
        question_count=normalized['count'],
        question_types=normalized['question_types'],
        difficulty=normalized['difficulty'],
        marks=normalized['marks'],
        language=normalized['language'],
        include_answers=normalized['include_answers'],
        year_from=normalized['year_from'],
        year_to=normalized['year_to'],
        status=GenerationRequest.STATUS_PROCESSING,
        generation_model=_model_name(chat_model),
        generation_version=GENERATION_VERSION,
    )

    try:
        built = ctx_fn(
            notebook,
            topic,
            year_from=normalized['year_from'],
            year_to=normalized['year_to'],
        )

        syllabus_rows = built.get('syllabus') or []
        history_rows = built.get('history') or []
        context_rows = syllabus_rows + history_rows
        notices = list(built.get('notices') or [])

        if not syllabus_rows:
            raise InsufficientSources(
                'This notebook has no usable syllabus material for that topic.'
            )

        alias_names = list(topic.aliases or [])
        messages = prompts.build_messages(
            {
                'count': normalized['count'],
                'question_types': normalized['question_types'],
                'difficulty': normalized['difficulty'],
                'marks': normalized['marks'],
                'language': normalized['language'],
                'include_answers': normalized['include_answers'],
                'year_from': normalized['year_from'],
                'year_to': normalized['year_to'],
            },
            syllabus_rows,
            history_rows,
            topic.name,
            alias_names,
        )

        envelope = _invoke_with_retries(chat_model, messages, request)

        existing_texts = _notebook_question_texts(notebook)
        syllabus_topic_unmatched = 'syllabus_topic_unmatched' in notices
        include_answers = normalized['include_answers']

        created = []
        validated_count = 0
        needs_review_count = 0

        with transaction.atomic():
            for item in envelope.questions[: normalized['count']]:
                item_dict = item.model_dump()
                (
                    status, source_refs, report, numeric_report,
                ) = validation.validate_question(
                    item_dict,
                    context_rows,
                    existing_texts,
                    question_type=item.question_type,
                    syllabus_topic_unmatched=syllabus_topic_unmatched,
                    requested_marks=normalized['marks'],
                )
                if status == GeneratedQuestion.VALIDATION_VALIDATED:
                    validated_count += 1
                else:
                    needs_review_count += 1

                # The numeric audit can contain the verified answer; never
                # persist or return it when the caller asked to hide answers.
                if not include_answers:
                    numeric_report = {}

                generated = GeneratedQuestion.objects.create(
                    notebook=notebook,
                    creator=user,
                    request=request,
                    topic=topic,
                    topic_ids=[topic.id],
                    question_text=item.prompt,
                    answer_text=item.answer if include_answers else '',
                    solution_text=(
                        (item.solution or '') if include_answers else ''
                    ),
                    question_type=item.question_type,
                    marks=item.marks,
                    difficulty=item.difficulty,
                    review_status=GeneratedQuestion.REVIEW_PENDING,
                    source_refs=source_refs,
                    language=item.language or normalized['language'],
                    marking_rubric=[r.model_dump() for r in item.marking_rubric],
                    generation_model=request.generation_model,
                    generation_version=GENERATION_VERSION,
                    validation_status=status,
                    validation_report=report,
                    answer_confidence=item.answer_confidence,
                    options=list(item.options or []),
                    numeric_report=numeric_report,
                )
                created.append(generated)
                existing_texts.append((item.prompt, 'generated'))

            total = len(created)
            requested_count = normalized['count']
            shortfall = max(0, requested_count - total)
            if shortfall:
                notices.append('short_batch')
            if total == 0:
                final_status = GenerationRequest.STATUS_FAILED
            elif validated_count == total:
                final_status = GenerationRequest.STATUS_COMPLETED
            else:
                final_status = GenerationRequest.STATUS_PARTIAL

            request.status = final_status
            request.questions_created = total
            request.questions_validated = validated_count
            request.questions_needs_review = needs_review_count
            request.request_meta = {
                'notices': notices,
                'requested_count': requested_count,
                'shortfall': shortfall,
                'syllabus_rows': len(syllabus_rows),
                'history_rows': len(history_rows),
                'took_ms': int((time.monotonic() - started) * 1000),
            }
            request.finished_at = timezone.now()
            request.save()

    except GenerationError as exc:
        _fail(request, exc)
        raise
    except Exception as exc:  # pragma: no cover - defensive safety net
        logger.exception(
            'generation_unexpected_error notebook=%s request=%s',
            notebook.pk, request.pk,
        )
        safe = GenerationError(
            'Practice-question generation failed safely; nothing was saved.'
        )
        _fail(request, safe)
        raise safe from exc

    logger.info(
        'generation_turn notebook=%s request=%s status=%s created=%d '
        'validated=%d needs_review=%d took_ms=%d',
        notebook.pk, request.pk, request.status, total,
        validated_count, needs_review_count,
        request.request_meta.get('took_ms', 0),
    )

    return _payload(request, created)


def _model_name(chat_model):
    """Best available model label for provenance (never a credential)."""
    return str(
        getattr(chat_model, 'model_name', '')
        or getattr(chat_model, 'model', '')
        or getattr(settings, 'GENERATION_LLM_MODEL', '')
    )


def _notebook_question_texts(notebook):
    """Past and previously generated texts for duplicate detection.

    Bounded and notebook-scoped. Each entry is ``(text, kind)`` so validation
    can distinguish a collision with a real past paper from a collision with
    an earlier generated question.
    """
    texts = []
    rows = Question.objects.filter(notebook=notebook).exclude(
        extraction_status='FAILED'
    ).order_by('-year')[:500]
    for row in rows:
        text = (row.normalized_text or row.raw_text or '').strip()
        if text:
            texts.append((text, 'past'))
    generated = GeneratedQuestion.objects.filter(
        notebook=notebook
    ).order_by('-created_at')[:500]
    for row in generated:
        text = (row.question_text or '').strip()
        if text:
            texts.append((text, 'generated'))
    return texts


def _fail(request, exc):
    request.status = GenerationRequest.STATUS_FAILED
    request.error_code = getattr(exc, 'code', 'generation_error')
    request.error_message = exc.message
    request.finished_at = timezone.now()
    request.save()


def _invoke_with_retries(chat_model, messages, request):
    """Invoke the model, retrying once on a schema failure.

    Any ``GenerationError`` (timeout, rate-limit, invalid response, ...) is
    recorded on the request as FAILED before it propagates, so a failed turn
    is always auditable rather than leaving the request stuck in PROCESSING.
    """
    retries = _int_setting('GENERATION_SCHEMA_RETRIES', 1)
    attempts = max(0, retries) + 1
    last = None
    try:
        for attempt in range(attempts):
            response, _took = model_module.invoke(chat_model, messages)
            try:
                return parse_answer(model_module.response_text(response))
            except LLMInvalidResponse as exc:
                last = exc
                logger.info(
                    'generation_schema_retry request=%s attempt=%d',
                    request.pk, attempt,
                )
    except GenerationError as exc:
        _fail(request, exc)
        raise
    _fail(request, last)
    raise last


def _payload(request, created):
    from ...serializers import (
        GeneratedQuestionDetailSerializer,
        GenerationRequestSerializer,
    )

    return {
        'request': GenerationRequestSerializer(request).data,
        'questions': GeneratedQuestionDetailSerializer(created, many=True).data,
    }
