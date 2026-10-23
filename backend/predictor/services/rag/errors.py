"""Safe, machine-readable errors for the Phase 4 RAG layer.

Every error carries a stable ``code`` that the API maps to an HTTP status,
plus a message that is safe to return to a client: no provider payloads, no
source text, no exception internals. Provider exceptions are translated into
these types at the boundary in ``embeddings.py``.
"""


class RAGError(Exception):
    """Base class for every failure the RAG layer reports to a caller."""

    code = 'rag_error'
    http_status = 500
    default_hint = ''

    def __init__(self, message, *, hint=None):
        super().__init__(message)
        self.message = message
        self.hint = hint if hint is not None else self.default_hint

    def as_dict(self):
        payload = {'code': self.code, 'message': self.message}
        if self.hint:
            payload['hint'] = self.hint
        return {'error': payload}


class InvalidQuery(RAGError):
    """Caller-supplied search input is missing or out of range."""

    code = 'invalid_query'
    http_status = 400


class EmbeddingUnavailable(RAGError):
    """The embedding provider cannot be reached or is not configured."""

    code = 'embedding_unavailable'
    http_status = 503


class QuotaExceeded(RAGError):
    """The embedding provider rejected the request for quota / rate limits."""

    code = 'quota_exceeded'
    http_status = 503


class EmbeddingTimeout(RAGError):
    """The embedding provider did not answer in time."""

    code = 'embedding_timeout'
    http_status = 504


class RetrievalTimeout(RAGError):
    """The vector store query exceeded ``RAG_QUERY_TIMEOUT_SECONDS``."""

    code = 'retrieval_timeout'
    http_status = 504


class DimensionMismatch(RAGError):
    """Configured, stored and returned dimensions disagree.

    Raised before writing a vector, before querying one, and when the
    embedding response does not have ``EMBEDDING_DIMENSION`` values. Never
    silently truncates or pads.
    """

    code = 'dimension_mismatch'
    http_status = 500
    default_hint = (
        'Set EMBEDDING_DIMENSION to match the existing vector column, or run '
        '`manage.py index_rag --reset-vectors` to rebuild the column and '
        're-embed every chunk.'
    )


class InvalidProviderResponse(RAGError):
    """The provider answered, but with something we cannot trust."""

    code = 'invalid_provider_response'
    http_status = 500


class VectorBackendUnavailable(RAGError):
    """PostgreSQL + pgvector is required for this operation but not usable."""

    code = 'vector_backend_unavailable'
    http_status = 503
    default_hint = (
        'Vector search needs PostgreSQL with pgvector. Point DATABASE_URL at a '
        'PostgreSQL database and enable the extension with '
        '`CREATE EXTENSION IF NOT EXISTS vector`.'
    )
