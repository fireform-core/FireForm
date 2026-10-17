"""The LLM base class every provider implements, plus the small types it returns."""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.api.schemas.enums import HealthState, LLMProvider
from app.services.llm.errors import LLMResponseError

# Health and model list calls should answer fast. A fill can take minutes, these can't.
PROBE_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class ModelInfo:
    name: str
    size_gb: float | None = None
    quantization: str | None = None
    loaded: bool | None = None


@dataclass(frozen=True)
class LLMHealth:
    status: HealthState
    provider: LLMProvider
    response_time_ms: int | None = None
    detail: str | None = None
    provider_version: str | None = None
    model_loaded: str | None = None
    models_available: list[ModelInfo] | None = None


class LLM(ABC):
    def __init__(self, provider: LLMProvider, model: str, timeout: int):
        self.provider = provider
        self.model = model
        self.timeout = timeout

    def generate_json(self, prompt: str, schema: dict, model: str | None = None) -> str:
        """Send the prompt and return the answer as JSON object text.

        schema is the JSON schema the answer should follow. model overrides the
        configured one for this call only.
        """
        raw = self._generate(prompt, schema, model or self.model)
        return parse_json_object(raw)

    @abstractmethod
    def _generate(self, prompt: str, schema: dict, model: str) -> str:
        """Return the raw text the model produced."""

    @abstractmethod
    def list_models(self) -> list[ModelInfo]:
        """Models the server offers. Raises an LLMError when it can't be reached."""

    @abstractmethod
    def health(self) -> LLMHealth:
        """Probe the server. Never raises."""


def parse_json_object(text: str) -> str:
    """Return text as clean JSON, or raise LLMResponseError.

    Providers that don't enforce a schema sometimes wrap the JSON in a code fence
    or a sentence, so fall back to the outermost braces.
    """
    for candidate in (text.strip(), text[text.find("{"): text.rfind("}") + 1]):
        try:
            value = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(value, dict):
            return candidate
    raise LLMResponseError(f"Model did not return a JSON object: {text[:200]!r}")
