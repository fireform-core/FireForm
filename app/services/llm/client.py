"""The one place FireForm talks to a model.

Every provider we support speaks the OpenAI chat completions API, so there is
one request shape, one response shape and one set of failures to handle. What
differs between providers lives in the table in providers.py, not here.

Two things in this file are load bearing and easy to undo by accident. The SDK
client is built with max_retries=0, because the SDK's own retries would sit
underneath the rate limit policy here and quietly turn ten attempts into thirty.
And the rate limit wait is deliberately long, because a 429 is the provider
asking us to wait, not telling us we are wrong.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, TypeVar

import openai
from openai import OpenAI

from app.core.logging import get_logger
from app.services.llm.errors import (
    LLMAuthError,
    LLMConfigError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from app.services.llm.gate import RateLimitGate
from app.services.llm.models import LLMSettings, ModelInfo, ProviderHealth
from app.services.llm.parsing import extract_json_object
from app.services.llm.providers import resolve

logger = get_logger(__name__)

T = TypeVar("T")

_OVERLOADED_STATUS = 529
_OPTIONAL_PARAMS = ("response_format", "max_tokens", "temperature")

_lock = threading.Lock()
_settings: LLMSettings | None = None
_client: OpenAI | None = None


def get_settings() -> LLMSettings:
    """Resolved provider settings, worked out once per process."""
    global _settings
    with _lock:
        if _settings is None:
            _settings = resolve()
        return _settings


def get_client() -> OpenAI:
    """The SDK client, built once per process."""
    global _client
    settings = get_settings()
    with _lock:
        if _client is None:
            _client = OpenAI(
                api_key=settings.api_key,
                base_url=settings.base_url,
                timeout=settings.timeout,
                default_headers=settings.extra_headers,
                max_retries=0,
            )
        return _client


def reset() -> None:
    """Drop the cached settings and client. Used by tests and after a reconfig."""
    global _settings, _client
    with _lock:
        _settings = None
        _client = None


def check_config() -> LLMSettings:
    """Resolve settings now so a bad configuration stops the process at startup.

    Raises LLMConfigError with a message naming the setting to fix.
    """
    settings = get_settings()
    where = settings.base_url or "the provider's default endpoint"
    logger.info(
        "LLM provider: %s, model %s, endpoint %s%s",
        settings.label,
        settings.model,
        where,
        ", prompts leave this machine" if settings.external else "",
    )
    return settings


def _retry_after(exc: Exception, fallback: float, ceiling: float) -> float:
    """How long to wait, preferring what the provider asked for."""
    response = getattr(exc, "response", None)
    header = None
    if response is not None:
        try:
            header = response.headers.get("retry-after")
        except Exception:
            header = None
    if header:
        try:
            asked = float(header)
        except ValueError:
            asked = fallback
        return min(max(asked, fallback), ceiling)
    return fallback


def _with_retries(call: Callable[[], T], *, what: str, gate: RateLimitGate | None = None) -> T:
    """Run one provider call, applying the rate limit and server error policy."""
    settings = get_settings()
    attempts = settings.rate_limit_retries + 1
    server_attempts = settings.server_retries + 1
    server_tries = 0

    for attempt in range(1, attempts + 1):
        if gate is not None:
            gate.check()
        try:
            return call()
        except openai.RateLimitError as exc:
            wait = _retry_after(exc, settings.rate_limit_wait, settings.rate_limit_max_wait)
            if attempt == attempts:
                error = LLMRateLimitError(
                    f"{settings.label} is still rate limiting after {attempts} attempts "
                    f"over about {int(wait * attempts)}s ({what})",
                    retry_after_seconds=wait,
                )
                if gate is not None:
                    gate.trip(error)
                logger.error("%s", error)
                raise error from exc
            logger.warning(
                "%s rate limited (attempt %d of %d), waiting %.0fs",
                settings.label,
                attempt,
                attempts,
                wait,
            )
            time.sleep(wait)
        except (openai.AuthenticationError, openai.PermissionDeniedError) as exc:
            raise LLMAuthError(
                f"{settings.label} rejected the API key. Check the key for this provider."
            ) from exc
        except openai.APITimeoutError as exc:
            raise LLMTimeoutError(
                f"{settings.label} did not answer within {settings.timeout}s ({what})"
            ) from exc
        except openai.APIConnectionError as exc:
            raise LLMUnavailableError(
                f"could not reach {settings.label} at "
                f"{settings.base_url or 'its default endpoint'}: {exc}"
            ) from exc
        except openai.APIStatusError as exc:
            status = getattr(exc, "status_code", None)
            if status == _OVERLOADED_STATUS:
                if attempt == attempts:
                    error = LLMRateLimitError(
                        f"{settings.label} reported itself overloaded on every attempt ({what})",
                        retry_after_seconds=settings.rate_limit_wait,
                    )
                    if gate is not None:
                        gate.trip(error)
                    raise error from exc
                time.sleep(
                    _retry_after(exc, settings.rate_limit_wait, settings.rate_limit_max_wait)
                )
                continue
            if status is not None and status >= 500:
                server_tries += 1
                if server_tries >= server_attempts:
                    raise LLMUnavailableError(
                        f"{settings.label} returned {status} on {server_tries} attempts ({what})"
                    ) from exc
                time.sleep(settings.server_retry_wait)
                continue
            raise LLMResponseError(f"{settings.label} rejected the request ({what}): {exc}") from exc

    raise LLMUnavailableError(f"{settings.label} could not be called ({what})")


def _named_param(message: str) -> str | None:
    """Which optional parameter an error message is complaining about."""
    lowered = message.lower()
    for name in _OPTIONAL_PARAMS:
        if name in lowered:
            return name
    return None


def _create(payload: dict[str, Any]) -> Any:
    """One chat completion, dropping any optional parameter the model refuses.

    Some hosted models reject a parameter instead of ignoring it, and which ones
    do changes with every release. Reading the complaint and trying again
    without that parameter is cheaper than keeping a compatibility matrix.
    """
    body = dict(payload)
    for _ in range(len(_OPTIONAL_PARAMS)):
        try:
            return get_client().chat.completions.create(**body)
        except openai.BadRequestError as exc:
            name = _named_param(str(exc))
            if name is None or name not in body:
                raise
            logger.warning("provider rejected %s, retrying without it", name)
            body.pop(name)
    return get_client().chat.completions.create(**body)


def _answer_text(response: Any, prefilled: bool) -> str:
    """The answer as text, with a prefilled opening brace put back."""
    choices = getattr(response, "choices", None) or []
    if not choices:
        raise LLMResponseError("the provider returned no answer")
    text = choices[0].message.content or ""
    if prefilled and not text.lstrip().startswith("{"):
        text = "{" + text
    return text


def generate(
    prompt: str,
    *,
    model: str | None = None,
    max_tokens: int | None = None,
    timeout: int | None = None,
    json_object: bool = False,
    gate: RateLimitGate | None = None,
) -> str:
    """Send one prompt and return the answer as text.

    `json_object` asks the provider for JSON where it supports that, and
    otherwise falls back to starting the answer with an opening brace. Callers
    that want a parsed object should use generate_json.
    """
    settings = get_settings()
    prefill = json_object and settings.json_prefill

    messages: list[dict[str, str]] = [{"role": "user", "content": prompt}]
    if prefill:
        messages.append({"role": "assistant", "content": "{"})

    payload: dict[str, Any] = {
        "model": model or settings.model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens or settings.max_tokens,
        "timeout": timeout or settings.timeout,
    }
    if json_object and settings.json_mode:
        payload["response_format"] = {"type": "json_object"}

    what = f"model {payload['model']}"
    response = _with_retries(lambda: _create(payload), what=what, gate=gate)
    return _answer_text(response, prefill)


def generate_json(
    prompt: str,
    *,
    model: str | None = None,
    max_tokens: int | None = None,
    timeout: int | None = None,
    gate: RateLimitGate | None = None,
) -> dict[str, Any]:
    """Send one prompt and return the JSON object the model answered with."""
    text = generate(
        prompt,
        model=model,
        max_tokens=max_tokens,
        timeout=timeout,
        json_object=True,
        gate=gate,
    )
    return extract_json_object(text)


def list_models() -> list[ModelInfo]:
    """Models the provider will serve, with the configured one marked.

    A provider that will not list them, because the key lacks the permission or
    the endpoint does not implement it, still gets an answer: the model this
    deployment is configured to use.
    """
    settings = get_settings()
    try:
        names = [model.id for model in get_client().models.list()]
    except Exception as exc:
        logger.warning("%s would not list models: %s", settings.label, exc)
        names = []

    if settings.model not in names:
        names.insert(0, settings.model)
    return [ModelInfo(name=name, default=name == settings.model) for name in names]


def health() -> ProviderHealth:
    """Whether the model backend is usable, without spending money to find out.

    A local provider is cheap to ask, so it gets asked. A hosted one is not
    probed: a listing call on every health check costs quota and rate limit
    headroom to answer a question the configuration already answers.
    """
    try:
        settings = get_settings()
    except LLMConfigError as exc:
        return ProviderHealth(
            provider="unknown",
            label="unknown",
            model="",
            external=False,
            status="unhealthy",
            probed=False,
            detail=str(exc),
        )

    base = {
        "provider": settings.provider,
        "label": settings.label,
        "model": settings.model,
        "external": settings.external,
    }

    if settings.external:
        return ProviderHealth(
            **base,
            status="healthy",
            probed=False,
            detail="hosted provider, not probed to avoid spending quota",
        )

    started = time.monotonic()
    try:
        get_client().models.list()
    except Exception as exc:
        return ProviderHealth(**base, status="unhealthy", probed=True, detail=str(exc))
    return ProviderHealth(
        **base,
        status="healthy",
        probed=True,
        response_time_ms=int((time.monotonic() - started) * 1000),
    )
