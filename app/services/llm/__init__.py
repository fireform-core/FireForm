"""Talking to language models.

The only part of FireForm that sends a prompt anywhere. Callers do

    from app.services import llm

    text = llm.get_registry().generate_json(prompt, schema, provider, model)

and never import the modules underneath. Several providers can be enabled at
once, each request picks one, and provider=None, model=None means the default.
The settings are read in settings.py, the registry lives in registry.py.
"""

from functools import lru_cache

from app.api.schemas.enums import LLMProvider
from app.services.llm.base import DownloadableModelInfo, LLM, LLMHealth, ModelInfo
from app.services.llm.errors import (
    LLMAuthError,
    LLMConfigError,
    LLMError,
    LLMExternalConsentError,
    LLMModelNotFoundError,
    LLMNotAvailableError,
    LLMRateLimitError,
    LLMResponseError,
    LLMSecretKeyError,
    LLMUnavailableError,
)
from app.services.llm.factory import create_llm
from app.services.llm.registry import LLMRegistry, ModelChoice, ProviderCatalog
from app.services.llm.settings import LLMSettings, ProviderSettings, load_settings
from app.services.llm.validator import ModelCheck, ModelValidator
from app.services.llm.user_config import effective_registry, registry_for_candidate


@lru_cache(maxsize=1)
def get_registry() -> LLMRegistry:
    """The enabled providers, built once per process. Tests reset it with get_registry.cache_clear()."""
    return LLMRegistry.from_settings(load_settings())


__all__ = [
    "DownloadableModelInfo",
    "LLM",
    "LLMAuthError",
    "LLMConfigError",
    "LLMError",
    "LLMExternalConsentError",
    "LLMHealth",
    "LLMModelNotFoundError",
    "LLMNotAvailableError",
    "LLMProvider",
    "LLMRateLimitError",
    "LLMRegistry",
    "LLMResponseError",
    "LLMSecretKeyError",
    "LLMSettings",
    "LLMUnavailableError",
    "ModelCheck",
    "ModelChoice",
    "ModelInfo",
    "ModelValidator",
    "ProviderCatalog",
    "ProviderSettings",
    "create_llm",
    "effective_registry",
    "get_registry",
    "load_settings",
    "registry_for_candidate",
]
