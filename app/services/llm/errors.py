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


class LLMSecretKeyError(LLMError):
    """The key required to encrypt provider credentials cannot be accessed."""

    status_code = 503
    error_code = "LLM_SECRET_KEY_UNAVAILABLE"


class LLMExternalConsentError(LLMError):
    """External processing has not been explicitly allowed."""

    status_code = 422
    error_code = "LLM_EXTERNAL_CONSENT_REQUIRED"


class LLMNotAvailableError(LLMError):
    """The request named a provider or model that isn't enabled or offered."""

    status_code = 422
    error_code = "LLM_NOT_AVAILABLE"


class LLMUnavailableError(LLMError):
    """The server could not be reached, timed out, or kept rate limiting us."""

    status_code = 503
    error_code = "LLM_UNAVAILABLE"


class LLMRateLimitError(LLMUnavailableError):
    """The server kept answering 429 after the retries: rate limited, or out of quota."""

    error_code = "LLM_RATE_LIMITED"


class LLMAuthError(LLMError):
    """The server rejected the API key."""

    error_code = "LLM_AUTH_FAILED"


class LLMModelNotFoundError(LLMError):
    """The server answered, but doesn't have the model that was asked for."""

    error_code = "LLM_MODEL_NOT_FOUND"


class LLMResponseError(LLMError):
    """The server answered, but not with a usable JSON object."""

    error_code = "LLM_BAD_RESPONSE"
