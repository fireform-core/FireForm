"""Talking to a language model.

The only part of FireForm that sends a prompt anywhere. Callers do

    from app.services import llm

    text = llm.get_llm().generate_json(prompt, schema)

and never import the modules underneath. Which server answers is a deployment
setting (LLM_PROVIDER), see factory.py.
"""

from functools import lru_cache

from app.api.schemas.enums import LLMProvider
from app.services.llm.base import LLM, LLMHealth, ModelInfo
from app.services.llm.errors import (
    LLMAuthError,
    LLMConfigError,
    LLMError,
    LLMResponseError,
    LLMUnavailableError,
)
from app.services.llm.factory import create_llm


@lru_cache(maxsize=1)
def get_llm() -> LLM:
    """The configured LLM, built once per process. Tests reset it with get_llm.cache_clear()."""
    return create_llm()


__all__ = [
    "LLM",
    "LLMAuthError",
    "LLMConfigError",
    "LLMError",
    "LLMHealth",
    "LLMProvider",
    "LLMResponseError",
    "LLMUnavailableError",
    "ModelInfo",
    "create_llm",
    "get_llm",
]
