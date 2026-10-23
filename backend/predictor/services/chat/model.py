"""LangChain chat-model factory and provider-exception translation.

``get_chat_model`` is the only place that reads ``GEMINI_API_KEY`` and the
only place that imports ``langchain_google_genai``; both are lazy so the
Django app boots (and the rest of the test suite runs) without the chat
extras. Configuration problems raise :class:`ChatUnavailable` *before* the
pipeline writes anything; runtime provider problems are translated to the
stable chat error codes below so a raw SDK/``TimeoutError`` can never reach
the API in another shape.
"""

import logging
import time

from django.conf import settings

from .errors import (
    ChatError,
    ChatUnavailable,
    LLMInvalidResponse,
    LLMRateLimited,
    LLMTimeout,
    LLMUnavailable,
)

logger = logging.getLogger(__name__)

SUPPORTED_PROVIDERS = ('google_genai',)


def get_chat_model():
    """Build the configured LangChain chat model, or raise ``ChatError``."""
    if not getattr(settings, 'CHAT_LLM_ENABLED', True):
        raise ChatUnavailable(
            'Notebook chat is disabled on this deployment.',
            hint='Set CHAT_LLM_ENABLED=true to turn it on.',
        )
    provider = (
        getattr(settings, 'CHAT_LLM_PROVIDER', '') or 'google_genai'
    ).strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise ChatUnavailable(
            f'Chat provider {provider!r} is not supported.',
            hint='Set CHAT_LLM_PROVIDER=' + SUPPORTED_PROVIDERS[0] + '.',
        )
    if not settings.GEMINI_API_KEY:
        raise ChatUnavailable(
            'Notebook chat needs a Gemini API key on the server.',
            hint='Set GEMINI_API_KEY in the backend environment.',
        )
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError as exc:
        raise ChatUnavailable(
            'The LangChain chat integration is not installed on the server.',
            hint=(
                'pip install langchain-core langchain-google-genai '
                '(see requirements.txt).'
            ),
        ) from exc
    return ChatGoogleGenerativeAI(
        model=settings.CHAT_LLM_MODEL,
        temperature=settings.CHAT_LLM_TEMPERATURE,
        max_output_tokens=settings.CHAT_LLM_MAX_OUTPUT_TOKENS,
        timeout=settings.CHAT_LLM_TIMEOUT_SECONDS,
        google_api_key=settings.GEMINI_API_KEY,
    )


def translate_exception(exc):
    """Map a raw provider/SDK exception onto the stable chat taxonomy."""
    message = str(exc)
    lowered = message.lower()
    code = getattr(exc, 'code', None)
    status = getattr(exc, 'status', None)
    if (
        code in (429, '429')
        or status in (429, '429')
        or 'resource_exhausted' in lowered
        or 'resource has been exhausted' in lowered
        or ('rate' in lowered and 'limit' in lowered)
        or 'quota' in lowered
    ):
        return LLMRateLimited(
            'The chat model rate-limited the request or ran out of quota.'
        )
    if isinstance(exc, TimeoutError) or 'timeout' in lowered or 'timed out' in lowered:
        return LLMTimeout('The chat model did not answer in time.')
    if (
        code in (401, 403, '401', '403')
        or 'api key' in lowered
        or 'permission' in lowered
        or 'unauthenticated' in lowered
        or 'permission_denied' in lowered
    ):
        return LLMUnavailable(
            'The chat model rejected the credentials for this request.'
        )
    logger.warning(
        'chat_provider_error type=%s code=%s', type(exc).__name__, code
    )
    return LLMUnavailable('The chat model could not be reached.')


def invoke(model, messages):
    """Call the model and translate every failure into a ``ChatError``.

    Returns ``(response, took_ms)``. Only IDs, counts and timings are ever
    logged — never prompt text, snippets or provider payloads.
    """
    started = time.monotonic()
    try:
        response = model.invoke(messages)
    except ChatError:
        # Already a translated chat error (e.g. a faked provider failure in
        # tests, or a re-invoked wrapper); never re-map its stable code.
        raise
    except TimeoutError as exc:
        raise LLMTimeout('The chat model did not answer in time.') from exc
    except Exception as exc:
        raise translate_exception(exc) from exc
    took_ms = int((time.monotonic() - started) * 1000)
    return response, took_ms


def response_text(response):
    """Extract plain text from an ``AIMessage`` (or a bare string)."""
    content = getattr(response, 'content', response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get('type') in (None, 'text'):
                    parts.append(str(block.get('text') or ''))
            else:
                text = getattr(block, 'text', None)
                if text:
                    parts.append(str(text))
        return ''.join(parts)
    return str(content)


__all__ = [
    'ChatUnavailable',
    'LLMInvalidResponse',
    'LLMRateLimited',
    'LLMTimeout',
    'LLMUnavailable',
    'SUPPORTED_PROVIDERS',
    'get_chat_model',
    'invoke',
    'response_text',
    'translate_exception',
]
