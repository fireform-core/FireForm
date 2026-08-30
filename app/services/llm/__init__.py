"""Talking to a language model.

This is the only part of FireForm that sends a prompt anywhere. Import from
here, never from the modules underneath, so that swapping a provider or changing
how retries work stays a change to one package.

    from app.services import llm

    fields = llm.generate_json(prompt)
    summary = llm.generate(prompt)

Which backend answers is a deployment setting, LLM_PROVIDER, not a per request
choice. Ollama, OpenAI, Gemini and Claude are supported by name, and "custom"
covers anything else that serves the OpenAI chat completions API.
"""

from app.services.llm.client import (
    check_config,
    generate,
    generate_json,
    get_settings,
    health,
    list_models,
    reset,
)
from app.services.llm.errors import (
    LLMAuthError,
    LLMConfigError,
    LLMError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from app.services.llm.gate import RateLimitGate
from app.services.llm.models import LLMSettings, ModelInfo, Provider, ProviderHealth
from app.services.llm.providers import PROVIDERS

__all__ = [
    "PROVIDERS",
    "LLMAuthError",
    "LLMConfigError",
    "LLMError",
    "LLMRateLimitError",
    "LLMResponseError",
    "LLMSettings",
    "LLMTimeoutError",
    "LLMUnavailableError",
    "ModelInfo",
    "Provider",
    "ProviderHealth",
    "RateLimitGate",
    "check_config",
    "generate",
    "generate_json",
    "get_settings",
    "health",
    "list_models",
    "reset",
]
