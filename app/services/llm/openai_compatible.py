"""Any server that speaks the OpenAI chat completions API.

That covers OpenAI itself, Gemini and Claude through their compatible endpoints,
Groq, OpenRouter, and self hosted servers like vLLM, LM Studio and llama.cpp.
Only the base URL and the API key differ.
"""

import time
from contextlib import contextmanager

import openai

from app.api.schemas.enums import HealthState, LLMProvider
from app.services.llm.base import LLM, PROBE_TIMEOUT_SECONDS, LLMHealth, ModelInfo
from app.services.llm.errors import LLMAuthError, LLMError, LLMResponseError, LLMUnavailableError


class OpenAICompatibleLLM(LLM):
    def __init__(
        self,
        provider: LLMProvider,
        base_url: str,
        api_key: str,
        model: str,
        timeout: int,
        max_retries: int = 3,
        structured_output: bool = True,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ):
        super().__init__(provider, model, timeout)
        self.base_url = base_url
        self.structured_output = structured_output
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.client = openai.OpenAI(
            base_url=base_url,
            api_key=api_key or "not-needed",
            timeout=timeout,
            max_retries=max_retries,
        )

    def _generate(self, prompt: str, schema: dict, model: str) -> str:
        # Optional settings are only sent when set, since some models reject them
        # (OpenAI reasoning models refuse temperature and max_tokens, for example)
        options = {}
        if self.structured_output:
            options["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "form_values", "schema": schema},
            }
        if self.max_tokens is not None:
            options["max_tokens"] = self.max_tokens
        if self.temperature is not None:
            options["temperature"] = self.temperature

        with self._translate_errors():
            completion = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                **options,
            )

        if not completion.choices:
            raise LLMResponseError(f"{self.provider.value} returned no choices")
        choice = completion.choices[0]
        if choice.finish_reason == "length":
            raise LLMResponseError(
                f"{self.provider.value} stopped at the output limit before finishing. Raise LLM_MAX_TOKENS."
            )
        return choice.message.content or ""

    def list_models(self) -> list[ModelInfo]:
        probe = self.client.with_options(timeout=PROBE_TIMEOUT_SECONDS, max_retries=0)
        with self._translate_errors():
            return [ModelInfo(name=m.id) for m in probe.models.list()]

    def health(self) -> LLMHealth:
        t0 = time.monotonic()
        try:
            models = self.list_models()
        except LLMError as exc:
            return LLMHealth(status=HealthState.unhealthy, provider=self.provider, detail=exc.message)
        return LLMHealth(
            status=HealthState.healthy,
            provider=self.provider,
            response_time_ms=int((time.monotonic() - t0) * 1000),
            models_available=models or None,
        )

    @contextmanager
    def _translate_errors(self):
        """Turn SDK exceptions into LLM errors. Order matters, subclasses first."""
        where = f"{self.provider.value} at {self.base_url}"
        try:
            yield
        except (openai.AuthenticationError, openai.PermissionDeniedError) as exc:
            raise LLMAuthError(f"{where} rejected the API key. Check LLM_API_KEY.") from exc
        except openai.RateLimitError as exc:
            raise LLMUnavailableError(f"{where} is still rate limiting after retries") from exc
        except openai.APITimeoutError as exc:
            raise LLMUnavailableError(f"{where} timed out") from exc
        except openai.APIConnectionError as exc:
            raise LLMUnavailableError(f"Could not reach {where}") from exc
        except openai.APIStatusError as exc:
            if exc.status_code >= 500:
                raise LLMUnavailableError(f"{where} returned {exc.status_code}") from exc
            raise LLMResponseError(f"{where} returned {exc.status_code}: {exc.message}") from exc
