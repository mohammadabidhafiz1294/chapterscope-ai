"""Safe, machine-readable errors for the Phase 7 generation pipeline.

Mirrors :mod:`predictor.services.chat.errors` and
:mod:`predictor.services.analytics.errors`: every failure carries a stable
``code`` the API maps to an HTTP status, plus a client-safe message (never a
provider payload, prompt text or raw exception). When a ``GenerationRequest``
was already persisted, the pipeline attaches it so the API can return
``request_id`` next to the error; that id is never part of the message.
"""


class GenerationError(Exception):
    """Base class for every failure the generation layer reports."""

    code = 'generation_error'
    http_status = 500
    default_hint = ''

    def __init__(self, message, *, hint=None):
        super().__init__(message)
        self.message = message
        self.hint = self.default_hint if hint is None else hint
        # Attached by the pipeline so the API can echo them; ``None`` when the
        # failure happened before the request row was written.
        self.request_id = None

    def as_dict(self):
        payload = {'error': {'code': self.code, 'message': self.message}}
        if self.hint:
            payload['error']['hint'] = self.hint
        return payload


class InvalidRequest(GenerationError):
    """Caller-supplied parameters are missing or out of range."""

    code = 'invalid_request'
    http_status = 400


class TopicNotFound(GenerationError):
    """The requested topic does not belong to this notebook."""

    code = 'topic_not_found'
    http_status = 404


class GenerationUnavailable(GenerationError):
    """Generation is disabled, unconfigured, or the integration is missing.

    Raised *before* the request row is written, so a misconfigured
    deployment never leaves a half-finished paper behind.
    """

    code = 'generation_unavailable'
    http_status = 503
    default_hint = (
        'Set GEMINI_API_KEY and keep GENERATION_LLM_ENABLED=true, '
        'or retry later.'
    )


class LLMUnavailable(GenerationError):
    """The model could not be reached or rejected the request."""

    code = 'llm_unavailable'
    http_status = 503


class LLMRateLimited(GenerationError):
    """The model rate-limited the request or exhausted its quota."""

    code = 'llm_rate_limited'
    http_status = 503
    default_hint = 'Retry shortly; the provider quota or rate limit was hit.'


class LLMTimeout(GenerationError):
    """The model did not answer within the configured budget."""

    code = 'llm_timeout'
    http_status = 504


class LLMInvalidResponse(GenerationError):
    """The model answered, but with something we cannot trust.

    Raised after the bounded schema retries are exhausted; nothing is
    persisted for the invalid output.
    """

    code = 'llm_invalid_response'
    http_status = 502
    default_hint = (
        'The model did not return the required JSON shape after retrying.'
    )


class InsufficientSources(GenerationError):
    """The notebook has no usable syllabus grounding for this topic."""

    code = 'insufficient_sources'
    http_status = 422
    default_hint = (
        'Attach and index a syllabus for this notebook that covers the '
        'selected topic, then retry.'
    )
