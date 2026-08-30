"""Which providers exist, and turning the environment into settings.

Every provider here speaks the OpenAI chat completions API, so the table below
holds only what differs: where to send the request, which key opens it, and
whether the provider can be made to answer in JSON. Adding a provider is a row.

Nothing here makes a network call. Resolving settings is pure, which is what
lets the backend refuse to start on a bad configuration instead of finding out
halfway through someone's incident report.
"""

from __future__ import annotations

import ipaddress
import json
from urllib.parse import urlparse

from app.core import config as app_config
from app.services.llm.errors import LLMConfigError
from app.services.llm.models import LLMSettings, Provider

PROVIDERS: dict[str, Provider] = {
    "ollama": Provider(
        name="ollama",
        label="Ollama",
        key_setting=None,
        key_required=False,
        default_base_url=None,
        base_url_required=False,
        json_mode=True,
        json_prefill=False,
        external=False,
        model_required=False,
    ),
    "openai": Provider(
        name="openai",
        label="OpenAI",
        key_setting="OPENAI_API_KEY",
        key_required=True,
        default_base_url=None,
        base_url_required=False,
        json_mode=True,
        json_prefill=False,
        external=True,
        model_required=True,
    ),
    "gemini": Provider(
        name="gemini",
        label="Google Gemini",
        key_setting="GEMINI_API_KEY",
        key_required=True,
        default_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        base_url_required=False,
        json_mode=True,
        json_prefill=False,
        external=True,
        model_required=True,
    ),
    "anthropic": Provider(
        name="anthropic",
        label="Anthropic Claude",
        key_setting="ANTHROPIC_API_KEY",
        key_required=True,
        default_base_url="https://api.anthropic.com/v1/",
        base_url_required=False,
        # Their compatibility layer documents response_format as ignored, so
        # asking for it would be a silent no-op. The prefill does the job.
        json_mode=False,
        json_prefill=True,
        external=True,
        model_required=True,
    ),
    "custom": Provider(
        name="custom",
        label="Custom endpoint",
        key_setting="LLM_API_KEY",
        key_required=False,
        default_base_url=None,
        base_url_required=True,
        json_mode=True,
        json_prefill=False,
        external=None,
        model_required=True,
    ),
}

# The SDK rejects an empty key before it sends anything, so an endpoint that
# needs no auth still gets a placeholder.
_NO_KEY_PLACEHOLDER = "not-needed"


def _is_local(url: str) -> bool:
    """True when a URL points at this machine or a private network.

    A hostname that does not parse as an IP is treated as remote, because
    guessing wrong in that direction is the safe way to guess wrong.
    """
    host = urlparse(url).hostname
    if not host:
        return False
    if host in {"localhost", "host.docker.internal"}:
        return True
    if "." not in host and ":" not in host:
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address.is_private


def _parse_headers(raw: str) -> dict[str, str] | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMConfigError(
            f"LLM_EXTRA_HEADERS is not valid JSON: {exc}. "
            'It should look like {"X-My-Header": "value"}.'
        ) from exc
    if not isinstance(parsed, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in parsed.items()
    ):
        raise LLMConfigError(
            'LLM_EXTRA_HEADERS must be a JSON object of strings, such as {"X-My-Header": "value"}.'
        )
    return parsed


def _resolve_base_url(provider: Provider, cfg) -> str | None:
    """Where requests go, preferring an explicit override."""
    if cfg.LLM_BASE_URL:
        return cfg.LLM_BASE_URL
    if provider.name == "ollama":
        return f"{cfg.OLLAMA_HOST}/v1"
    return provider.default_base_url


def resolve(cfg=None) -> LLMSettings:
    """Build the settings for the configured provider, or explain what is wrong.

    `cfg` is the config module, read at call time rather than bound as a default
    so tests can hand over a stand-in instead of editing the environment.
    """
    cfg = cfg or app_config
    provider = PROVIDERS.get(cfg.LLM_PROVIDER)
    if provider is None:
        known = ", ".join(sorted(PROVIDERS))
        raise LLMConfigError(
            f"LLM_PROVIDER is set to {cfg.LLM_PROVIDER!r}, which is not a provider. "
            f"Pick one of: {known}."
        )

    base_url = _resolve_base_url(provider, cfg)
    if provider.base_url_required and not base_url:
        raise LLMConfigError(
            f"LLM_PROVIDER={provider.name} needs LLM_BASE_URL set to an endpoint "
            "that serves the OpenAI chat completions API, such as "
            "http://localhost:8001/v1."
        )

    model = cfg.LLM_MODEL or (cfg.OLLAMA_MODEL if provider.name == "ollama" else "")
    if not model:
        raise LLMConfigError(
            f"LLM_PROVIDER={provider.name} needs LLM_MODEL set. "
            f"{provider.label} has no default here on purpose, because a model name "
            "pinned in source goes stale."
        )

    api_key = getattr(cfg, provider.key_setting, "") if provider.key_setting else ""
    if provider.key_required and not api_key:
        raise LLMConfigError(f"LLM_PROVIDER={provider.name} needs {provider.key_setting} set.")

    external = provider.external
    if external is None:
        external = not _is_local(base_url or "")

    if external and not cfg.LLM_ALLOW_EXTERNAL:
        raise LLMConfigError(
            f"LLM_PROVIDER={provider.name} sends incident narratives to {provider.label}, "
            "which means names, addresses and medical detail leave this machine. "
            "Set LLM_ALLOW_EXTERNAL=true to allow that, or use a local provider."
        )

    if cfg.LLM_RATE_LIMIT_RETRIES < 0 or cfg.LLM_RATE_LIMIT_WAIT_SECONDS < 0:
        raise LLMConfigError(
            "LLM_RATE_LIMIT_RETRIES and LLM_RATE_LIMIT_WAIT_SECONDS cannot be negative."
        )
    if cfg.LLM_TIMEOUT <= 0 or cfg.LLM_MAX_TOKENS <= 0:
        raise LLMConfigError("LLM_TIMEOUT and LLM_MAX_TOKENS must be greater than zero.")

    return LLMSettings(
        provider=provider.name,
        label=provider.label,
        model=model,
        base_url=base_url,
        api_key=api_key or _NO_KEY_PLACEHOLDER,
        timeout=cfg.LLM_TIMEOUT,
        max_tokens=cfg.LLM_MAX_TOKENS,
        json_mode=provider.json_mode,
        json_prefill=provider.json_prefill,
        external=external,
        extra_headers=_parse_headers(cfg.LLM_EXTRA_HEADERS),
        rate_limit_retries=cfg.LLM_RATE_LIMIT_RETRIES,
        rate_limit_wait=cfg.LLM_RATE_LIMIT_WAIT_SECONDS,
        rate_limit_max_wait=cfg.LLM_RATE_LIMIT_MAX_WAIT_SECONDS,
        respect_retry_after=cfg.LLM_RESPECT_RETRY_AFTER,
        server_retries=cfg.LLM_SERVER_RETRIES,
        server_retry_wait=cfg.LLM_SERVER_RETRY_WAIT_SECONDS,
    )
