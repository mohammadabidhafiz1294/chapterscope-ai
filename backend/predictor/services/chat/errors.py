"""Safe, machine-readable errors for the Phase 6 chat pipeline.

Every error carries a stable ``code`` that the API maps to an HTTP status,
plus a message that is safe to return to a client: no provider payloads, no
source text, no exception internals. When a user message was already
persisted, the pipeline attaches it (``user_message``) and the request id so
the API can return them next to the error; they are never part of the error
message itself.
"""


class ChatError(Exception):
    """Base class for every failure the chat layer reports to a caller."""

    code = 'chat_error'
    http_status = 500
    default_hint = ''

    def __init__(self, message, *, hint=None):
        super().__init__(message)
        self.message = message
        self.hint = hint if hint is not None else self.default_hint
        # Attached by the pipeline so the API can echo them; plain strings /
        # dicts only. ``None`` when the failure happened before any write.
        self.request_id = None
        self.user_message = None

    def as_dict(self):
        payload = {'error': {'code': self.code, 'message': self.message}}
        if self.hint:
            payload['error']['hint'] = self.hint
        return payload


class InvalidRequest(ChatError):
    """Caller-supplied chat input is missing or out of range."""

    code = 'invalid_request'
    http_status = 400


class ChatUnavailable(ChatError):
    """Chat is disabled, unconfigured, or the integration is not installed.

    Raised *before* anything is written, so a misconfigured deployment never
    leaves half a conversation behind.
    """

    code = 'chat_unavailable'
    http_status = 503
    default_hint = (
        'Set GEMINI_API_KEY and keep CHAT_LLM_ENABLED=true, or retry later.'
    )


class LLMUnavailable(ChatError):
    """The chat model could not be reached or rejected the request."""

    code = 'llm_unavailable'
    http_status = 503


class LLMRateLimited(ChatError):
    """The chat model rate-limited the request or exhausted the quota."""

    code = 'llm_rate_limited'
    http_status = 503
    default_hint = 'Retry shortly; the provider quota or rate limit was hit.'


class LLMTimeout(ChatError):
    """The chat model did not answer within the configured budget."""

    code = 'llm_timeout'
    http_status = 504


class LLMInvalidResponse(ChatError):
    """The model answered, but with something we cannot trust."""

    code = 'llm_invalid_response'
    http_status = 502
    default_hint = 'Retry the turn; the model returned an unusable payload.'
