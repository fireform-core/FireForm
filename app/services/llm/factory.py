"""Build the LLM the deployment asked for, from app.core.config.

Every setting is checked here, so a bad config fails at startup with a message
that names the setting to fix, not on the first fill.
"""

import ipaddress
from urllib.parse import urlparse

from app.api.schemas.enums import LLMProvider
from app.core import config
from app.services.llm.base import LLM
from app.services.llm.errors import LLMConfigError
from app.services.llm.ollama import OllamaLLM
from app.services.llm.openai_compatible import OpenAICompatibleLLM


def create_llm(cfg=config) -> LLM:
    try:
        provider = LLMProvider(cfg.LLM_PROVIDER)
    except ValueError:
        raise LLMConfigError(
            f"LLM_PROVIDER={cfg.LLM_PROVIDER!r} is not supported. "
            f"Use one of: {', '.join(p.value for p in LLMProvider)}."
        ) from None
    timeout = _parse_int("LLM_TIMEOUT", cfg.LLM_TIMEOUT, cfg.OLLAMA_TIMEOUT)

    # Hosted providers only differ by URL and key setting. No default models:
    # vendor model names go stale, so every provider but Ollama must set LLM_MODEL.
    match provider:
        case LLMProvider.ollama:
            return OllamaLLM(
                host=_check_url(cfg.LLM_BASE_URL or cfg.OLLAMA_HOST),
                model=cfg.LLM_MODEL or cfg.OLLAMA_MODEL,
                timeout=timeout,
            )
        case LLMProvider.openai:
            return _openai_compatible(cfg, provider, timeout, "https://api.openai.com/v1", "OPENAI_API_KEY")
        case LLMProvider.gemini:
            return _openai_compatible(
                cfg, provider, timeout, "https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY"
            )
        case LLMProvider.anthropic:
            # Anthropic's compatible endpoint ignores response_format and needs an output cap
            return _openai_compatible(
                cfg, provider, timeout, "https://api.anthropic.com/v1/", "ANTHROPIC_API_KEY",
                structured_output=False, max_tokens=12288,
            )
        case LLMProvider.custom:
            return _openai_compatible(cfg, provider, timeout, default_url="", key_setting="LLM_API_KEY")


def _openai_compatible(
    cfg,
    provider: LLMProvider,
    timeout: int,
    default_url: str,
    key_setting: str,
    structured_output: bool = True,
    max_tokens: int | None = None,
) -> OpenAICompatibleLLM:
    """Check the settings shared by every OpenAI compatible provider and build it.

    default_url, structured_output and max_tokens are the provider's defaults.
    LLM_BASE_URL, LLM_STRUCTURED_OUTPUT and LLM_MAX_TOKENS override them.
    """
    base_url = cfg.LLM_BASE_URL or default_url
    if not base_url:
        raise LLMConfigError("LLM_PROVIDER=custom needs LLM_BASE_URL, such as http://vllm:8000/v1.")
    _check_url(base_url)
    if not cfg.LLM_MODEL:
        raise LLMConfigError(f"LLM_PROVIDER={provider.value} needs LLM_MODEL.")

    api_key = getattr(cfg, key_setting) or cfg.LLM_API_KEY
    if provider != LLMProvider.custom and not api_key:
        raise LLMConfigError(f"LLM_PROVIDER={provider.value} needs {key_setting}.")

    # Incident text holds names, addresses and medical detail. Sending it off
    # the local network has to be a deliberate choice.
    if not is_local_url(base_url) and not _parse_bool("LLM_ALLOW_EXTERNAL", cfg.LLM_ALLOW_EXTERNAL, False):
        raise LLMConfigError(
            f"{base_url} is outside the local network, so incident data would leave this machine. "
            "Set LLM_ALLOW_EXTERNAL=true to allow it."
        )

    return OpenAICompatibleLLM(
        provider=provider,
        base_url=base_url,
        api_key=api_key,
        model=cfg.LLM_MODEL,
        timeout=timeout,
        max_retries=_parse_int("LLM_MAX_RETRIES", cfg.LLM_MAX_RETRIES, 3),
        structured_output=_parse_bool("LLM_STRUCTURED_OUTPUT", cfg.LLM_STRUCTURED_OUTPUT, structured_output),
        max_tokens=_parse_int("LLM_MAX_TOKENS", cfg.LLM_MAX_TOKENS, max_tokens),
        temperature=_parse_float("LLM_TEMPERATURE", cfg.LLM_TEMPERATURE),
    )


def is_local_url(url: str) -> bool:
    """True for localhost, private IPs, and bare names like Docker service names."""
    host = urlparse(url).hostname or ""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return host == "localhost" or "." not in host or host.endswith((".local", ".internal", ".lan"))
    return ip.is_loopback or ip.is_private


def _check_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise LLMConfigError(f"{url!r} is not a valid URL. It should look like http://host:port.")
    return url


def _parse_int(name: str, raw: str, default: int | None = None) -> int | None:
    if raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        raise LLMConfigError(f"{name}={raw!r} should be a whole number.") from None


def _parse_float(name: str, raw: str) -> float | None:
    if raw == "":
        return None
    try:
        return float(raw)
    except ValueError:
        raise LLMConfigError(f"{name}={raw!r} should be a number.") from None


def _parse_bool(name: str, raw: str, default: bool) -> bool:
    if raw == "":
        return default
    if raw.lower() in ("true", "1", "yes"):
        return True
    if raw.lower() in ("false", "0", "no"):
        return False
    raise LLMConfigError(f"{name}={raw!r} should be true or false.")
