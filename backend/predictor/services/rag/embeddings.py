"""Configurable Gemini embeddings for the Phase 4 RAG layer.

Provider-side only: no database access, no chunk bookkeeping. The backend is
chosen with environment settings (``EMBEDDING_PROVIDER``,
``EMBEDDING_MODEL``, ``EMBEDDING_DIMENSION``), texts are sent in bounded
batches, and every failure is translated into a safe
:class:`predictor.services.rag.errors.RAGError` carrying a stable code.

``gemini-embedding-001`` is a Matryoshka representation: when
``output_dimensionality`` is below 3072 the client has to L2-normalize the
values itself, so every vector returned here is normalized. Normalization also
means cosine distance and dot product agree, which is what the HNSW index and
the dense query rely on.

Contract for :meth:`GeminiEmbeddingProvider.embed`: inputs are non-blank and
at most ``EMBEDDING_MAX_TEXT_CHARS`` characters (``indexing`` enforces this
when it chunks text), the result has exactly one vector per input, and the
vector has exactly ``EMBEDDING_DIMENSION`` values.
"""

import logging
import math
import time
from dataclasses import dataclass
from typing import List, Sequence

from django.conf import settings

from .errors import (
    DimensionMismatch,
    EmbeddingTimeout,
    EmbeddingUnavailable,
    InvalidProviderResponse,
    QuotaExceeded,
    RAGError,
)

logger = logging.getLogger(__name__)

TASK_DOCUMENT = 'document'
TASK_QUERY = 'query'

# Retry only transient failures; a 4xx is never retried.
_RETRY_BACKOFF_SECONDS = 0.15

# Modules whose exception messages may echo what we sent, so they are logged
# by class name + status code only (never the message, never our text).
_UNSAFE_EXC_MODULES = ('google.genai', 'httpx', 'requests', 'urllib3', 'h11')


@dataclass(frozen=True)
class EmbeddingConfig:
    provider: str
    model: str
    dimension: int
    document_task: str
    query_task: str
    batch_size: int
    max_text_chars: int
    timeout_seconds: float
    max_retries: int
    enabled: bool
    api_key: str


def get_config() -> EmbeddingConfig:
    provider = getattr(settings, 'EMBEDDING_PROVIDER', 'gemini') or 'gemini'
    return EmbeddingConfig(
        provider=provider.strip(),
        model=getattr(settings, 'EMBEDDING_MODEL', '').strip(),
        dimension=int(settings.EMBEDDING_DIMENSION),
        document_task=getattr(
            settings, 'EMBEDDING_TASK_TYPE_DOCUMENT', 'RETRIEVAL_DOCUMENT'
        ),
        query_task=getattr(
            settings, 'EMBEDDING_TASK_TYPE_QUERY', 'RETRIEVAL_QUERY'
        ),
        batch_size=max(1, int(getattr(settings, 'EMBEDDING_BATCH_SIZE', 16))),
        max_text_chars=max(
            1, int(getattr(settings, 'EMBEDDING_MAX_TEXT_CHARS', 8000))
        ),
        timeout_seconds=float(getattr(settings, 'EMBEDDING_TIMEOUT_SECONDS', 10)),
        max_retries=max(0, int(getattr(settings, 'EMBEDDING_MAX_RETRIES', 2))),
        enabled=bool(getattr(settings, 'EMBEDDING_ENABLED', True)),
        api_key=(getattr(settings, 'GEMINI_API_KEY', '') or '').strip(),
    )


class GeminiEmbeddingProvider:
    """Embeds text with the Gemini API via the official ``google-genai`` SDK."""

    name = 'gemini'

    def __init__(self, config: EmbeddingConfig):
        self.config = config
        self._client = None

    # -- client -----------------------------------------------------------
    @property
    def client(self):
        if self._client is None:
            from google.genai import Client, types

            self._client = Client(
                api_key=self.config.api_key,
                http_options=types.HttpOptions(
                    timeout=int(self.config.timeout_seconds * 1000)
                ),
            )
        return self._client

    # -- public API -------------------------------------------------------
    def embed(
        self, texts: Sequence[str], *, task: str = TASK_DOCUMENT
    ) -> List[List[float]]:
        """Return one L2-normalized vector per input text, in input order."""
        self._validate_inputs(texts)
        if not self.config.enabled:
            raise EmbeddingUnavailable(
                'RAG embedding is disabled on this deployment.',
                hint='Set EMBEDDING_ENABLED=true to enable vector indexing.',
            )
        if not self.config.model:
            raise EmbeddingUnavailable(
                'No embedding model is configured.',
                hint='Set EMBEDDING_MODEL (for example gemini-embedding-001).',
            )
        if not self.config.api_key:
            raise EmbeddingUnavailable(
                'No embedding credentials are configured.',
                hint='Set GEMINI_API_KEY to enable vector indexing.',
            )

        task_type = (
            self.config.document_task
            if task == TASK_DOCUMENT
            else self.config.query_task
        )
        vectors = []
        for start in range(0, len(texts), self.config.batch_size):
            batch = list(texts[start:start + self.config.batch_size])
            vectors.extend(self._embed_batch(batch, task_type))
        return vectors

    def embed_query(self, text: str) -> List[float]:
        return self.embed([text], task=TASK_QUERY)[0]

    # -- internals --------------------------------------------------------
    def _validate_inputs(self, texts: Sequence[str]) -> None:
        if not texts:
            raise ValueError('embed() needs at least one text')
        for text in texts:
            if not isinstance(text, str) or not text.strip():
                raise ValueError('embed() refuses blank texts')
            if len(text) > self.config.max_text_chars:
                raise ValueError(
                    f'text of {len(text)} chars exceeds the '
                    f'{self.config.max_text_chars} char embedding limit'
                )

    def _embed_batch(self, texts: List[str], task_type: str) -> List[List[float]]:
        from google.genai import types

        attempts = self.config.max_retries + 1
        for attempt in range(1, attempts + 1):
            started = time.monotonic()
            try:
                response = self.client.models.embed_content(
                    model=self.config.model,
                    contents=list(texts),
                    config=types.EmbedContentConfig(
                        task_type=task_type,
                        output_dimensionality=self.config.dimension,
                        auto_truncate=True,
                    ),
                )
            except Exception as exc:
                error = _translate(exc)
                _log_failure(self.config, task_type, len(texts), attempt, error, exc)
                if not _is_retryable(error) or attempt >= attempts:
                    raise error from exc
                time.sleep(_RETRY_BACKOFF_SECONDS * attempt)
                continue

            try:
                vectors = _extract(response, self.config.dimension, len(texts))
            except RAGError as error:
                _log_failure(self.config, task_type, len(texts), attempt, error, None)
                raise
            logger.info(
                'embed ok model=%s task=%s texts=%d dim=%d attempt=%d took_ms=%d',
                self.config.model, task_type, len(texts), self.config.dimension,
                attempt, int((time.monotonic() - started) * 1000),
            )
            return vectors
        raise EmbeddingUnavailable(  # pragma: no cover - loop always returns/raises
            'The embedding provider failed.'
        )


def _extract(response, dimension: int, expected: int) -> List[List[float]]:
    embeddings = getattr(response, 'embeddings', None)
    if not embeddings or len(embeddings) != expected:
        raise InvalidProviderResponse(
            'The embedding provider returned an unexpected number of vectors.',
            hint='Retry the request; if it persists, check the configured '
                 'embedding model.',
        )
    vectors = []
    for entry in embeddings:
        values = list(getattr(entry, 'values', None) or [])
        if len(values) != dimension:
            raise DimensionMismatch(
                f'The embedding provider returned {len(values)} dimensions but '
                f'EMBEDDING_DIMENSION is {dimension}.'
            )
        vectors.append(_normalize(values, dimension))
    return vectors


def _normalize(values: List[float], dimension: int) -> List[float]:
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0.0 or not math.isfinite(norm):
        raise InvalidProviderResponse(
            'The embedding provider returned an unusable vector.'
        )
    return [value / norm for value in values]


def _translate(exc: Exception) -> RAGError:
    """Map a provider exception onto a safe, stable RAG error."""
    from google.genai import errors as genai_errors

    if isinstance(exc, RAGError):
        return exc
    if isinstance(exc, genai_errors.APIError):
        code = getattr(exc, 'code', None)
        if code == 429:
            return QuotaExceeded('The embedding provider rate-limited the request.')
        if code in (401, 403):
            return EmbeddingUnavailable(
                'The embedding credentials were rejected.',
                hint='Check that GEMINI_API_KEY is valid.',
            )
        if code == 400:
            return InvalidProviderResponse(
                'The embedding provider rejected the request.', hint=None
            )
        if isinstance(code, int) and code >= 500:
            return EmbeddingUnavailable('The embedding provider is unavailable.')
        return EmbeddingUnavailable('The embedding provider rejected the request.')
    if _is_timeout(exc):
        return EmbeddingTimeout('The embedding provider did not respond in time.')
    if type(exc).__module__.startswith('google.genai'):
        return InvalidProviderResponse('The embedding provider could not be called.')
    if isinstance(exc, (ConnectionError, OSError)) or 'transport' in type(exc).__name__:
        return EmbeddingUnavailable('The embedding provider could not be reached.')
    return EmbeddingUnavailable('The embedding provider failed.')


def _is_timeout(exc: Exception) -> bool:
    return isinstance(exc, TimeoutError) or 'timeout' in type(exc).__name__.lower()


def _is_retryable(error: RAGError) -> bool:
    return isinstance(error, (EmbeddingTimeout, EmbeddingUnavailable))


def translate_exception(exc: Exception) -> RAGError:
    """Map any exception raised while embedding onto a safe ``RAGError``.

    The provider already translates inside ``_embed_batch``; callers that go
    through the module-level helpers (fake providers today, another provider
    tomorrow) use this boundary so a raw ``TimeoutError`` or SDK exception can
    never escape to the API and break the documented error contract.
    """
    return _translate(exc)


def _log_failure(config, task_type, texts, attempt, error, exc) -> None:
    # Never log str(exc): provider messages can echo the text we sent.
    detail = type(exc).__name__ if exc is not None else ''
    status = getattr(exc, 'code', None)
    module = (type(exc).__module__ if exc is not None else '') or ''
    logger.warning(
        'embed failed provider=%s model=%s task=%s texts=%d attempt=%d '
        'error=%s status=%s cause=%s',
        config.provider, config.model, task_type, texts, attempt,
        error.code, status, detail,
    )
    if exc is not None and not module.startswith(_UNSAFE_EXC_MODULES):
        # Local bug: a traceback is safe and far more useful than a class name.
        logger.warning('embed raised a local error', exc_info=True)


_PROVIDERS = {
    'gemini': GeminiEmbeddingProvider,
}

_provider_cache = {}


def get_provider() -> GeminiEmbeddingProvider:
    """Build (and cache) the configured provider.

    Patch this function in tests to install a deterministic fake.
    """
    config = get_config()
    if not config.enabled:
        raise EmbeddingUnavailable(
            'RAG embedding is disabled on this deployment.',
            hint='Set EMBEDDING_ENABLED=true to enable vector indexing.',
        )
    provider_class = _PROVIDERS.get(config.provider)
    if provider_class is None:
        raise EmbeddingUnavailable(
            f'Embedding provider {config.provider!r} is not supported.',
            hint='Set EMBEDDING_PROVIDER=gemini.',
        )
    cache_key = (
        config.provider, config.model, config.dimension, config.timeout_seconds,
        config.max_retries,
    )
    provider = _provider_cache.get(cache_key)
    if provider is None:
        provider = provider_class(config)
        _provider_cache[cache_key] = provider
    return provider


def embed_documents(texts: Sequence[str]) -> List[List[float]]:
    return get_provider().embed(list(texts), task=TASK_DOCUMENT)


def embed_query(text: str) -> List[float]:
    return get_provider().embed_query(text)


def forget_providers() -> None:
    """Drop cached providers (used when settings change inside a process)."""
    _provider_cache.clear()
