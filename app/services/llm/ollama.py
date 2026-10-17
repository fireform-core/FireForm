"""Ollama through its native API.

Ollama also serves an OpenAI compatible endpoint, but that one can't set the
context size or the seed. Large forms need the 32k context, so we stay native.
"""

import time

import requests

from app.api.schemas.enums import HealthState, LLMProvider
from app.services.llm.base import LLM, PROBE_TIMEOUT_SECONDS, LLMHealth, ModelInfo
from app.services.llm.errors import LLMError, LLMResponseError, LLMUnavailableError

OPTIONS = {
    "num_ctx": 32768,
    # Backstop for runaway generation; the largest real output (ICS 209) is ~8k tokens
    "num_predict": 12288,
    "temperature": 0,
    "seed": 42,
    "repeat_penalty": 1.0,
    "repeat_last_n": 0,
}


class OllamaLLM(LLM):
    def __init__(self, host: str, model: str, timeout: int):
        super().__init__(LLMProvider.ollama, model, timeout)
        self.host = host.rstrip("/")

    def _generate(self, prompt: str, schema: dict, model: str) -> str:
        # The schema goes in as `format`, so Ollama constrains the output to it
        payload = {
            "model": model,
            "prompt": prompt,
            "format": schema,
            "stream": False,
            "think": False,
            "options": OPTIONS,
        }
        body = self._request("post", "/api/generate", json=payload, timeout=self.timeout)
        return body.get("response", "")

    def list_models(self) -> list[ModelInfo]:
        return self._to_models(self._request("get", "/api/tags"), self._running())

    def health(self) -> LLMHealth:
        t0 = time.monotonic()
        try:
            tags = self._request("get", "/api/tags")
        except LLMError as exc:
            return LLMHealth(status=HealthState.unhealthy, provider=self.provider, detail=exc.message)
        elapsed = int((time.monotonic() - t0) * 1000)

        running = self._running()
        return LLMHealth(
            status=HealthState.healthy,
            provider=self.provider,
            response_time_ms=elapsed,
            provider_version=self._version(),
            model_loaded=running[0] if running else None,
            models_available=self._to_models(tags, running) or None,
        )

    def _running(self) -> list[str]:
        """Names of the models loaded in memory right now. Empty if unknown."""
        try:
            return [m.get("name", "") for m in self._request("get", "/api/ps").get("models", [])]
        except LLMError:
            return []

    def _version(self) -> str | None:
        try:
            return self._request("get", "/api/version").get("version")
        except LLMError:
            return None

    @staticmethod
    def _to_models(tags: dict, running: list[str]) -> list[ModelInfo]:
        return [
            ModelInfo(
                name=m["name"],
                size_gb=round(m.get("size", 0) / (1024 ** 3), 2),
                quantization=m.get("details", {}).get("quantization_level"),
                loaded=m["name"] in running,
            )
            for m in tags.get("models", [])
            if m.get("name")
        ]

    def _request(self, method: str, path: str, timeout: int = PROBE_TIMEOUT_SECONDS, **kwargs) -> dict:
        """Call Ollama and return the JSON body, turning failures into LLM errors."""
        url = self.host + path
        try:
            response = requests.request(method, url, timeout=timeout, **kwargs)
        except requests.Timeout as exc:
            raise LLMUnavailableError(f"Ollama at {self.host} timed out") from exc
        except requests.RequestException as exc:
            raise LLMUnavailableError(f"Could not reach Ollama at {self.host}: {exc}") from exc

        if response.status_code >= 500:
            raise LLMUnavailableError(f"Ollama returned {response.status_code}: {response.text[:200]}")
        if response.status_code >= 400:
            raise LLMResponseError(f"Ollama returned {response.status_code}: {response.text[:200]}")
        try:
            return response.json()
        except ValueError as exc:
            raise LLMResponseError(f"Ollama returned a non JSON body from {path}") from exc
