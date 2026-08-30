"""What can go wrong when talking to a model.

Every provider reaches the rest of the app through these, so a caller never has
to know whether it was Ollama refusing a connection or Gemini refusing a key.
The split is by what the caller should do about it: give up now, wait and try
later, or treat the answer as unusable and move on.
"""

from __future__ import annotations


class LLMError(RuntimeError):
    """Base for everything this module raises."""


class LLMConfigError(LLMError):
    """The provider settings do not make sense. Raised at startup, not mid request."""


class LLMUnavailableError(LLMError):
    """The provider could not be reached, so nothing is extractable right now."""


class LLMAuthError(LLMError):
    """The key was rejected. Never retried, since it will be rejected again."""


class LLMRateLimitError(LLMError):
    """Still rate limited after every retry was used up.

    Carries the wait the provider last asked for, so the caller can pass a
    useful Retry-After to whoever asked for the extraction.
    """

    def __init__(self, message: str, retry_after_seconds: float | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class LLMResponseError(LLMError):
    """The call went through but the answer is unusable. One prompt's problem."""


class LLMTimeoutError(LLMResponseError):
    """The call ran past the timeout. Rarely worth retrying, the second try takes as long."""
