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
from app.services.llm.errors import (
    LLMAuthError,
    LLMError,
    LLMModelNotFoundError,
    LLMRateLimitError,
    LLMResponseError,
    LLMUnavailableError,
)
from app.services.llm.specs import SPECS


class OpenAICompatibleLLM(LLM):
    def __init__(
        self,
        provider: LLMProvider,
        base_url: str,
        api_key: str,
        model: str | None,
        timeout: int,
        max_retries: int = 3,
        structured_output: bool = True,
        max_tokens: int | None = None,
        temperature: float | None = None,
        headers: dict[str, str] | None = None,
        listed_id_prefix: str = "",
    ):
        super().__init__(provider, model, timeout)
        self.base_url = base_url
        self._secret = api_key or ""
        self.structured_output = structured_output
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.listed_id_prefix = listed_id_prefix
        self.client = openai.OpenAI(
            base_url=base_url,
            api_key=self._secret or "not-needed",
            timeout=timeout,
            max_retries=max_retries,
            default_headers=headers,
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

        with self._translate_errors(model):
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
                f"{self.provider.value} stopped at the output limit before finishing. "
                f"Raise {SPECS[self.provider].setting('MAX_TOKENS')}."
            )
        return choice.message.content or ""

    def list_models(self) -> list[ModelInfo]:
        probe = self.client.with_options(timeout=PROBE_TIMEOUT_SECONDS, max_retries=0)
        with self._translate_errors():
            return [ModelInfo(name=m.id.removeprefix(self.listed_id_prefix)) for m in probe.models.list()]

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
    def _translate_errors(self, model: str | None = None):
        """Turn SDK exceptions into LLM errors that say what to fix.

        model is set for a prompt and None for the model list, so a 404 can be
        told apart: a missing model, or a base URL that points somewhere wrong.
        Order matters, subclasses first.
        """
        spec = SPECS[self.provider]
        name = self.provider.value
        try:
            yield
        except (openai.AuthenticationError, openai.PermissionDeniedError) as exc:
            raise self._auth_error(exc) from exc
        except openai.RateLimitError as exc:
            raise LLMRateLimitError(
                f"{name} is still rate limiting after retries, or the account is out of quota: "
                f"{_reason(exc, self._secret)}"
            ) from exc
        except openai.APITimeoutError as exc:
            raise LLMUnavailableError(f"{name} at {self.base_url} timed out") from exc
        except openai.APIConnectionError as exc:
            raise LLMUnavailableError(
                f"Could not reach {name} at {self.base_url}. Check {spec.setting('BASE_URL')} and the network."
            ) from exc
        except openai.APIStatusError as exc:
            reason = _reason(exc, self._secret)
            # Gemini answers a bad key with 400 instead of 401
            if exc.status_code == 400 and "api key" in reason.lower():
                raise self._auth_error(exc) from exc
            if exc.status_code == 404 and model:
                raise LLMModelNotFoundError(f"{name} has no model {model}: {reason}") from exc
            if exc.status_code == 404:
                raise LLMResponseError(
                    f"{name} at {self.base_url} has no model list ({reason}). Check {spec.setting('BASE_URL')}."
                ) from exc
            if exc.status_code >= 500:
                raise LLMUnavailableError(f"{name} had a server error {exc.status_code}: {reason}") from exc
            raise LLMResponseError(f"{name} refused the request with {exc.status_code}: {reason}") from exc

    def _auth_error(self, exc: openai.APIStatusError) -> LLMAuthError:
        return LLMAuthError(
            f"{self.provider.value} rejected the API key: {_reason(exc, self._secret)}. "
            f"Check {SPECS[self.provider].setting('API_KEY')}."
        )


def _reason(exc: openai.APIStatusError, secret: object = "") -> str:
    """The provider's own error message, without the JSON around it.

    Bodies differ: OpenAI sends {"error": {"message"}}, Gemini a list of those,
    Anthropic {"type": "error", "error": {"message"}}.
    """
    body = exc.body
    if isinstance(body, list) and body:
        body = body[0]
    message = exc.message.rstrip(".")
    if isinstance(body, dict):
        error = body.get("error", body)
        if isinstance(error, dict) and error.get("message"):
            message = str(error["message"]).rstrip(".")
        elif isinstance(error, str):
            message = error.rstrip(".")
    if isinstance(secret, str) and len(secret) >= 8 and secret != "not-needed":
        message = message.replace(secret, "[redacted]")
    return message
