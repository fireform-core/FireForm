"""Checks that the configured models exist and actually answer.

check_config() runs at startup and returns warnings for the log. probe() sends
one short prompt, for POST /system/llm/test.
"""

import logging
import time
from dataclasses import dataclass

from app.api.schemas.enums import LLMProvider
from app.services.llm.errors import LLMError
from app.services.llm.registry import LLMRegistry

logger = logging.getLogger(__name__)

PROBE_PROMPT = 'This is a connection test. Reply with the JSON object {"ok": true} and nothing else.'
PROBE_SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}


@dataclass(frozen=True)
class ModelCheck:
    provider: LLMProvider
    model: str
    ok: bool
    latency_ms: int | None = None
    detail: str | None = None
    error_code: str | None = None


class ModelValidator:
    def __init__(self, registry: LLMRegistry):
        self.registry = registry

    def check_config(self) -> list[str]:
        """Warnings about the LLM settings. Asks every provider, so it is slow-ish."""
        warnings = list(self.registry.settings.warnings)
        default = self.registry.default

        for listing in self.registry.catalog(refresh=True):
            name = listing.provider.value
            if not listing.available:
                warnings.append(f"Could not check the {name} models. {listing.detail}")
                continue
            setting = self.registry.settings.providers[listing.provider].spec.setting("MODELS")
            warnings.extend(
                f"{setting} has {model}, but {name} does not offer it. It is left out of the model list."
                for model in listing.missing
            )
            if listing.provider is default.provider and not listing.offers(default.model):
                warnings.append(f"{name} does not offer the default model {default.model}. Fills will fail.")
        return warnings

    def probe(self, provider: LLMProvider | str | None = None, model: str | None = None) -> ModelCheck:
        """Send one short prompt. Raises only when the pair isn't enabled at all.

        The provider's own list isn't consulted first: the prompt is the stronger
        test, and its error says what went wrong.
        """
        choice = self.registry.resolve(provider, model, verify=False)
        t0 = time.monotonic()
        try:
            self.registry.client(choice.provider).generate_json(PROBE_PROMPT, PROBE_SCHEMA, choice.model)
        except LLMError as exc:
            logger.warning(
                "LLM test of %s %s failed with %s",
                choice.provider.value,
                choice.model,
                exc.error_code,
            )
            return ModelCheck(
                choice.provider, choice.model, ok=False, latency_ms=_since(t0),
                detail=exc.message, error_code=exc.error_code,
            )
        return ModelCheck(choice.provider, choice.model, ok=True, latency_ms=_since(t0))


def _since(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)
