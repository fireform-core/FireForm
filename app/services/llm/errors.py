"""Errors raised by the LLM package.

They extend AppError so a route that lets them through returns the right status
code without any extra handling.
"""

from app.core.errors.base import AppError


class LLMError(AppError):
    status_code = 502
    error_code = "LLM_ERROR"

    def __init__(self, message: str):
        super().__init__(message, status_code=self.status_code, error_code=self.error_code)


class LLMConfigError(LLMError):
    """The LLM settings are missing or invalid. Raised at startup."""

    status_code = 500
    error_code = "LLM_CONFIG_ERROR"


class LLMUnavailableError(LLMError):
    """The server could not be reached, timed out, or kept rate limiting us."""

    status_code = 503
    error_code = "LLM_UNAVAILABLE"


class LLMAuthError(LLMError):
    """The server rejected the API key."""

    error_code = "LLM_AUTH_FAILED"


class LLMResponseError(LLMError):
    """The server answered, but not with a usable JSON object."""

    error_code = "LLM_BAD_RESPONSE"
