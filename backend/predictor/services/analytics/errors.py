"""Machine-readable error contract for the Phase 5 analytics layer.

Mirrors ``predictor.services.rag.errors``: every failure the API can raise
carries a stable ``code`` plus an HTTP status, and is serialised through
``AnalyticsError.as_dict()`` so the response body always has the shape
``{"error": {"code": ..., "message": ..., "hint": ...}}``. Raw ORM or
provider exceptions never reach the view layer.
"""

from __future__ import annotations


class AnalyticsError(Exception):
    """Base class for every analytics failure surfaced by the API."""

    code = 'analytics_error'
    http_status = 500
    default_hint = ''

    def __init__(self, message: str, *, hint: str | None = None):
        super().__init__(message)
        self.message = message
        self.hint = self.default_hint if hint is None else hint

    def as_dict(self) -> dict:
        payload = {'code': self.code, 'message': self.message}
        if self.hint:
            payload['hint'] = self.hint
        return {'error': payload}


class InvalidRequest(AnalyticsError):
    """A parameter, id or payload violated a documented constraint."""

    code = 'invalid_request'
    http_status = 400


class TopicNotFound(AnalyticsError):
    """The requested topic does not belong to this notebook."""

    code = 'topic_not_found'
    http_status = 404


class LLMUnavailable(AnalyticsError):
    """No usable LLM (missing key, disabled or provider/network failure)."""

    code = 'llm_unavailable'
    http_status = 503
    default_hint = (
        'Set GEMINI_API_KEY (and TOPIC_LLM_ENABLED=true), or call with '
        'use_llm=false for the deterministic workflow.'
    )


class LLMInvalidResponse(AnalyticsError):
    """The LLM answered, but the answer failed strict validation."""

    code = 'llm_invalid_response'
    http_status = 502
    default_hint = 'Nothing was persisted for the entries that failed validation.'
