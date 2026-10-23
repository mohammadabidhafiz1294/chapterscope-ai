"""One deterministic chat turn over a notebook's indexed sources.

Order of operations (deliberate):

1. validate the user text (400 before any write),
2. resolve the chat model (503 before any write if disabled/unconfigured),
3. load the bounded recent history (the current question is not yet stored),
4. persist the USER message and bump the session,
5. notebook-filtered retrieval,
6. model call, strict JSON validation, citation filtering,
7. persist the ASSISTANT message with server-built source references.

Failures after step 4 keep the user message and return it beside the error.
No hidden reasoning, provider payloads or prompt text is ever stored or
logged. Tests inject ``model``/``search`` and never call a real provider.
"""

import json
import logging
import time
import uuid

from django.conf import settings
from django.db import transaction
from pydantic import ValidationError

from ...models import ChatMessage
from ..rag.errors import RAGError
from . import context, model as model_module, prompts
from .errors import (
    ChatError,
    InvalidRequest,
    LLMInvalidResponse,
)
from .schema import ChatAnswer

logger = logging.getLogger(__name__)

INSUFFICIENT_MESSAGE = (
    "I couldn't find enough evidence in this notebook's indexed sources to "
    'answer that. Try rephrasing, or add or re-index the relevant syllabus '
    'and past papers.'
)


def respond(session, text, *, model=None, search=None):
    """Run one chat turn and return the exchange payload.

    ``model`` and ``search`` are injectable for tests; the defaults resolve
    the configured LangChain client and the Phase 4 RAG search.
    """
    started = time.monotonic()
    request_id = uuid.uuid4().hex
    user_text = validate_message(text)
    chat_model = model if model is not None else model_module.get_chat_model()
    search_fn = search if search is not None else _default_search

    history = context.load_history(session)
    user_message = _persist_user_message(session, user_text)
    user_payload = _serialize_message(user_message)

    try:
        results, retrieval_ms = search_fn(session.notebook, user_text)
    except RAGError as exc:
        _attach(exc, request_id, user_payload)
        raise

    if not results:
        assistant, meta = _finish(
            session, INSUFFICIENT_MESSAGE, status='insufficient_evidence',
            sources=[], retrieved=0, request_id=request_id,
            history=history, retrieval_ms=retrieval_ms, llm_ms=0,
            started=started,
        )
        return _exchange(user_payload, assistant, [], 'insufficient_evidence', meta)

    try:
        answer, sources, status, llm_ms = generate(
            chat_model, history, results, user_text
        )
    except ChatError as exc:
        _attach(exc, request_id, user_payload)
        raise

    assistant, meta = _finish(
        session, answer, status=status, sources=sources,
        retrieved=len(results), request_id=request_id, history=history,
        retrieval_ms=retrieval_ms, llm_ms=llm_ms, started=started,
    )
    return _exchange(user_payload, assistant, sources, status, meta)


def validate_message(text):
    """Normalize and range-check the user's text before anything is written."""
    cleaned = ' '.join((text or '').split())
    if not cleaned:
        raise InvalidRequest('Message must not be empty.')
    cap = int(getattr(settings, 'CHAT_MAX_MESSAGE_CHARS', 4000))
    if len(cleaned) > cap:
        raise InvalidRequest(
            f'Message is {len(cleaned)} characters; the limit is {cap}.'
        )
    return cleaned


def generate(chat_model, history, results, user_text):
    """Model call + validation + citation filtering.

    Returns ``(answer, sources, status, llm_ms)``. ``status`` is ``'answered'``
    or ``'insufficient_evidence'``; in the latter case the answer is the
    deterministic fallback text and ``sources`` is empty, so uncited model
    prose is never persisted.
    """
    messages = prompts.build_messages(history, results, user_text)
    response, llm_ms = model_module.invoke(chat_model, messages)
    parsed = parse_answer(model_module.response_text(response))
    cap = int(getattr(settings, 'CHAT_MAX_ANSWER_CHARS', 4000))
    answer = (parsed.answer or '').strip()
    if not answer:
        raise LLMInvalidResponse('The model returned an empty answer.')
    if parsed.insufficient_evidence:
        return INSUFFICIENT_MESSAGE, [], 'insufficient_evidence', llm_ms
    sources = filter_citations(parsed.citations, results)
    if not sources:
        return INSUFFICIENT_MESSAGE, [], 'insufficient_evidence', llm_ms
    if len(answer) > cap:
        answer = answer[:cap].rstrip() + '…'
    return answer, sources, 'answered', llm_ms


def parse_answer(raw):
    """Strictly decode the model's JSON into ``ChatAnswer``."""
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
        return ChatAnswer.model_validate(data)
    except ValidationError as exc:
        raise LLMInvalidResponse(
            'The model response did not match the answer schema.'
        ) from exc


def filter_citations(citations, results):
    """Keep only citations that name a retrieved ``source_key``.

    All display fields are rebuilt from the retrieval row — never taken from
    the model. A quote is kept only when it appears verbatim in the snippet;
    unknown keys and duplicates are dropped. The list is capped by
    ``CHAT_MAX_CITATIONS``.
    """
    by_key = {row['source_key']: row for row in results}
    limit = int(getattr(settings, 'CHAT_MAX_CITATIONS', 5))
    seen = set()
    kept = []
    for citation in citations or []:
        key = (citation.source_key or '').strip()
        if not key or key in seen or key not in by_key:
            continue
        seen.add(key)
        row = by_key[key]
        quote = (citation.quote or '').strip()
        snippet = str(row.get('snippet') or '')
        if quote and quote not in snippet:
            quote = ''
        kept.append(source_reference(row, quote=quote))
        if len(kept) >= max(1, limit):
            break
    return kept


def source_reference(row, *, quote=''):
    """Server-built citation payload from one retrieval row."""
    return {
        'source_key': row.get('source_key'),
        'source_type': row.get('source_type'),
        'document_title': row.get('document_title'),
        'page_number': row.get('page_number'),
        'question_number': row.get('question_number'),
        'year': row.get('year'),
        'snippet': row.get('snippet'),
        'similarity': row.get('similarity'),
        'quote': quote,
    }


def _default_search(notebook, user_text):
    """Notebook-filtered retrieval via the Phase 4 RAG layer."""
    from ..rag import retrieval

    params = context.retrieval_params()
    query = context.retrieval_query(
        user_text, query_chars=params['query_chars']
    )
    payload = retrieval.search(
        notebook, query, keyword=params['keyword'], limit=params['top_k']
    )
    results = context.filter_results(
        payload.get('results') or [], params['min_score']
    )
    results = context.bound_sources(results)
    return results, int((payload.get('meta') or {}).get('took_ms') or 0)


def _persist_user_message(session, user_text):
    """Store the user turn and bump the session (one transaction)."""
    with transaction.atomic():
        message = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_USER,
            content=user_text,
            metadata={},
        )
        updates = ['updated_at']
        if not (session.title or '').strip():
            session.title = user_text[:60]
            updates.append('title')
        session.save(update_fields=updates)
    return message


def _persist_assistant_message(session, content, *, metadata):
    return ChatMessage.objects.create(
        session=session,
        role=ChatMessage.ROLE_ASSISTANT,
        content=content,
        metadata=metadata,
    )


def _finish(session, content, *, status, sources, retrieved, request_id,
            history, retrieval_ms, llm_ms, started):
    """Persist the assistant turn and log the (ID-only) summary."""
    meta = {
        'status': status,
        'sources': sources,
        'model': getattr(settings, 'CHAT_LLM_MODEL', ''),
        'request_id': request_id,
        'retrieved': int(retrieved),
        'cited': len(sources),
        'retrieval_ms': int(retrieval_ms or 0),
        'llm_ms': int(llm_ms or 0),
        'took_ms': int((time.monotonic() - started) * 1000),
    }
    assistant = _persist_assistant_message(session, content, metadata=meta)
    logger.info(
        'chat_turn notebook=%s session=%s request_id=%s status=%s '
        'retrieved=%d cited=%d history=%d retrieval_ms=%d llm_ms=%d '
        'took_ms=%d',
        session.notebook_id, session.pk, request_id, status, meta['retrieved'],
        meta['cited'], len(history), meta['retrieval_ms'], meta['llm_ms'],
        meta['took_ms'],
    )
    return assistant, meta


def _attach(exc, request_id, user_message):
    """Give an already-persisted turn to an error the API will return."""
    exc.request_id = request_id
    exc.user_message = user_message


def _serialize_message(message):
    from ...serializers import ChatMessageSerializer

    return ChatMessageSerializer(message).data


def _exchange(user_payload, assistant, sources, status, meta):
    return {
        'status': status,
        'user_message': user_payload,
        'assistant_message': _serialize_message(assistant),
        'sources': sources,
        'meta': meta,
    }
