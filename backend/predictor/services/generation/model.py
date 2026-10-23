"""LangChain chat-model factory and provider-exception translation (Phase 7).

Mirrors :mod:`predictor.services.chat.model`. ``get_generation_model`` is the
only place that reads ``GEMINI_API_KEY`` for this phase and the only place
that imports ``langchain_google_genai``; both are lazy so the Django app
boots (and the rest of the test suite runs) without the extras. Configuration
problems raise :class:`GenerationUnavailable` *before* the request row is
written; runtime provider problems are translated to the stable generation
error codes so a raw SDK/``TimeoutError`` can never reach the API in another
shape.
"""

import logging
import re
import time

from django.conf import settings

from .errors import (
    GenerationError,
    GenerationUnavailable,
    LLMRateLimited,
    LLMTimeout,
    LLMUnavailable,
)

logger = logging.getLogger(__name__)

SUPPORTED_PROVIDERS = ('google_genai',)


def get_generation_model():
    """Build the configured LangChain chat model, or raise ``GenerationError``."""
    if not getattr(settings, 'GENERATION_LLM_ENABLED', True):
        raise GenerationUnavailable(
            'Practice-question generation is disabled on this deployment.',
            hint='Set GENERATION_LLM_ENABLED=true to turn it on.',
        )
    provider = (
        getattr(settings, 'GENERATION_LLM_PROVIDER', '') or 'google_genai'
    ).strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise GenerationUnavailable(
            f'Generation provider {provider!r} is not supported.',
            hint='Set GENERATION_LLM_PROVIDER=' + SUPPORTED_PROVIDERS[0] + '.',
        )
    if not settings.GEMINI_API_KEY:
        raise GenerationUnavailable(
            'Practice-question generation needs a Gemini API key on the server.',
            hint='Set GEMINI_API_KEY in the backend environment.',
        )
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError as exc:
        raise GenerationUnavailable(
            'The LangChain chat integration is not installed on the server.',
            hint=(
                'pip install langchain-core langchain-google-genai '
                '(see requirements.txt).'
            ),
        ) from exc
    return ChatGoogleGenerativeAI(
        model=settings.GENERATION_LLM_MODEL,
        temperature=settings.GENERATION_LLM_TEMPERATURE,
        max_output_tokens=settings.GENERATION_LLM_MAX_OUTPUT_TOKENS,
        timeout=settings.GENERATION_LLM_TIMEOUT_SECONDS,
        google_api_key=settings.GEMINI_API_KEY,
    )


def translate_exception(exc):
    """Map a raw provider/SDK exception onto the stable generation taxonomy."""
    message = str(exc)
    lowered = message.lower()
    code = getattr(exc, 'code', None)
    status = getattr(exc, 'status', None)
    if (
        code in (429, '429')
        or status in (429, '429')
        or bool(re.search(r'\b429\b', message))
        or 'resource_exhausted' in lowered
        or 'resource has been exhausted' in lowered
        or ('rate' in lowered and 'limit' in lowered)
        or 'quota' in lowered
    ):
        return LLMRateLimited(
            'The generation model rate-limited the request or ran out of quota.'
        )
    if isinstance(exc, TimeoutError) or 'timeout' in lowered or 'timed out' in lowered:
        return LLMTimeout('The generation model did not answer in time.')
    if (
        code in (401, 403, '401', '403')
        or 'api key' in lowered
        or 'permission' in lowered
        or 'unauthenticated' in lowered
        or 'permission_denied' in lowered
    ):
        return LLMUnavailable(
            'The generation model rejected the credentials for this request.'
        )
    logger.warning(
        'generation_provider_error type=%s code=%s', type(exc).__name__, code
    )
    return LLMUnavailable('The generation model could not be reached.')


def invoke(model, messages):
    """Call the model and translate every failure into a ``GenerationError``.

    Returns ``(response, took_ms)``. Only IDs, counts and timings are ever
    logged — never prompt text, snippets or provider payloads.
    """
    started = time.monotonic()
    try:
        response = model.invoke(messages)
    except GenerationError:
        # Already a translated generation error (e.g. a faked provider
        # failure in tests); never re-map its stable code.
        raise
    except TimeoutError as exc:
        raise LLMTimeout('The generation model did not answer in time.') from exc
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
