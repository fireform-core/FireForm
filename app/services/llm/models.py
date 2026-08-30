"""Data shapes used across the LLM module.

Plain dataclasses, not Pydantic and not ORM models. Nothing here is an HTTP
body or a table; the API schemas that wrap these live in app/api/schemas/.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    """One backend, described by what makes it different from the others.

    `external=None` means it depends on the URL, which is the custom endpoint
    case. `json_prefill` starts the answer with an opening brace, the only lever
    available on a provider that has no JSON mode.
    """

    name: str
    label: str
    key_setting: str | None
    key_required: bool
    default_base_url: str | None
    base_url_required: bool
    json_mode: bool
    json_prefill: bool
    external: bool | None
    model_required: bool


@dataclass(frozen=True)
class LLMSettings:
    """Everything one call needs, resolved once and reused."""

    provider: str
    label: str
    model: str
    base_url: str | None
    api_key: str
    timeout: int
    max_tokens: int
    json_mode: bool
    json_prefill: bool
    external: bool
    extra_headers: dict[str, str] | None
    rate_limit_retries: int
    rate_limit_wait: float
    rate_limit_max_wait: float
    respect_retry_after: bool
    server_retries: int
    server_retry_wait: float


@dataclass(frozen=True)
class ModelInfo:
    """One model the provider will answer to."""

    name: str
    default: bool = False


@dataclass(frozen=True)
class ProviderHealth:
    """Whether the model backend is usable, for the health endpoint."""

    provider: str
    label: str
    model: str
    external: bool
    status: str
    probed: bool
    detail: str | None = None
    response_time_ms: int | None = None
