"""Read the LLM settings from app.core.config into one object per provider.

Every setting is checked here, so a bad config shows up at startup with a
message that names the setting to fix, not on the first fill.

A mistake in the default provider's settings stops startup, since every fill
that names no model goes there. A mistake in any other provider turns that
provider off with a warning, so the rest keep working.
"""

import ipaddress
from dataclasses import dataclass, field
from urllib.parse import urlparse

from app.api.schemas.enums import LLMProvider
from app.core import config
from app.services.llm.errors import LLMConfigError
from app.services.llm.selection import ModelSelection
from app.services.llm.specs import DEFAULT_OLLAMA_INSTALLABLE_MODELS, SPECS, ProviderSpec


@dataclass(frozen=True)
class ProviderSettings:
    spec: ProviderSpec
    base_url: str
    models: ModelSelection
    default_model: str | None
    api_key: str = field(default="", repr=False)
    timeout: int = 300
    pull_timeout: int = 120
    installable_models: tuple[str, ...] = ()
    max_retries: int = 3
    temperature: float | None = None
    structured_output: bool = True
    max_tokens: int | None = None
    manual_models: tuple[str, ...] = ()

    @property
    def provider(self) -> LLMProvider:
        return self.spec.provider


@dataclass(frozen=True)
class LLMSettings:
    providers: dict[LLMProvider, ProviderSettings]
    default_provider: LLMProvider
    warnings: tuple[str, ...] = field(default=())

    @property
    def default_model(self) -> str:
        return self.providers[self.default_provider].default_model


@dataclass(frozen=True)
class _Shared:
    """Settings every provider uses."""

    timeout: int
    max_retries: int
    temperature: float | None
    allow_external: bool


def load_settings(cfg=config) -> LLMSettings:
    try:
        default = LLMProvider(cfg.LLM_PROVIDER)
    except ValueError:
        raise LLMConfigError(
            f"LLM_PROVIDER={cfg.LLM_PROVIDER!r} is not supported. "
            f"Use one of: {', '.join(p.value for p in LLMProvider)}."
        ) from None

    shared = _Shared(
        timeout=_parse_int("LLM_TIMEOUT", cfg.LLM_TIMEOUT, cfg.OLLAMA_TIMEOUT),
        max_retries=_parse_int("LLM_MAX_RETRIES", cfg.LLM_MAX_RETRIES, 3),
        temperature=_parse_float("LLM_TEMPERATURE", cfg.LLM_TEMPERATURE),
        allow_external=_parse_bool("LLM_ALLOW_EXTERNAL", cfg.LLM_ALLOW_EXTERNAL, False),
    )

    providers: dict[LLMProvider, ProviderSettings] = {}
    warnings: list[str] = []
    for spec in SPECS.values():
        env = cfg.LLM_PROVIDER_ENV.get(spec.provider.value, {})
        is_default = spec.provider is default
        try:
            loaded = _load_provider(spec, env, shared, cfg, is_default)
        except LLMConfigError as exc:
            if is_default:
                raise
            warnings.append(f"{spec.provider.value} is off: {exc.message}")
            continue
        if loaded:
            providers[spec.provider] = loaded

    if default not in providers:
        models = SPECS[default].setting("MODELS")
        raise LLMConfigError(
            f"LLM_PROVIDER={default.value}, but {models} is empty so {default.value} is off. "
            f"Add {models}={_model_hint(cfg)}, or set LLM_PROVIDER to a provider that is on."
        )
    return LLMSettings(providers=providers, default_provider=default, warnings=tuple(warnings))


def _load_provider(
    spec: ProviderSpec, env: dict[str, str], shared: _Shared, cfg, is_default: bool
) -> ProviderSettings | None:
    """One provider's settings, or None when it is off. Raises on a mistake."""
    models = ModelSelection.parse(env.get("MODELS", ""))
    if models.is_empty:
        if env.get("API_KEY"):
            models_setting = spec.setting("MODELS")
            raise LLMConfigError(
                f"{spec.setting('API_KEY')} is set but {models_setting} is empty. "
                f"Add {models_setting}={_model_hint(cfg) if is_default else '<model name>'}, "
                f"a comma separated list, or * for every model {spec.provider.value} lists."
            )
        return None

    base_url = env.get("BASE_URL") or spec.default_base_url
    if not base_url:
        raise LLMConfigError(f"{spec.setting('BASE_URL')} is needed, such as http://vllm:8000/v1.")
    _check_url(spec.setting("BASE_URL"), base_url)

    api_key = env.get("API_KEY", "")
    if spec.needs_key and not api_key:
        raise LLMConfigError(
            f"{spec.setting('API_KEY')} is needed. Add it, or empty {spec.setting('MODELS')} "
            f"to turn {spec.provider.value} off."
        )

    # Incident text holds names, addresses and medical detail. Sending it off
    # the local network has to be a deliberate choice.
    if not is_local_url(base_url) and not shared.allow_external:
        raise LLMConfigError(
            f"{base_url} is outside the local network, so incident data would leave this machine. "
            "Set LLM_ALLOW_EXTERNAL=true to allow it."
        )

    pull_timeout = 120
    installable_models = ()
    if spec.provider is LLMProvider.ollama:
        pull_timeout = _parse_int(
            "OLLAMA_PULL_TIMEOUT",
            str(getattr(cfg, "OLLAMA_PULL_TIMEOUT", 120)),
            120,
        ) or 120
        installable_raw = getattr(cfg, "OLLAMA_INSTALLABLE_MODELS", "") or env.get("INSTALLABLE_MODELS", "")
        if installable_raw:
            installable_models = tuple(dict.fromkeys(n.strip() for n in installable_raw.split(",") if n.strip()))
        else:
            installable_models = DEFAULT_OLLAMA_INSTALLABLE_MODELS

    return ProviderSettings(
        spec=spec,
        base_url=base_url,
        models=models,
        default_model=_default_model(spec, models, cfg, is_default),
        api_key=api_key,
        timeout=shared.timeout,
        pull_timeout=pull_timeout,
        installable_models=installable_models,
        max_retries=shared.max_retries,
        temperature=shared.temperature,
        structured_output=_parse_bool(
            spec.setting("STRUCTURED_OUTPUT"), env.get("STRUCTURED_OUTPUT", ""), spec.structured_output
        ),
        max_tokens=_parse_int(spec.setting("MAX_TOKENS"), env.get("MAX_TOKENS", ""), spec.max_tokens),
    )


def _default_model(spec: ProviderSpec, models: ModelSelection, cfg, is_default: bool) -> str | None:
    """The model a request gets when it names this provider but no model.

    LLM_MODEL for the default provider, then OLLAMA_MODEL for Ollama, then the
    first name in <PREFIX>_MODELS. None when the list is * and nothing else says.
    """
    if is_default and cfg.LLM_MODEL:
        if not models.allows(cfg.LLM_MODEL):
            raise LLMConfigError(
                f"LLM_MODEL={cfg.LLM_MODEL} is not in {spec.setting('MODELS')}. Add it there, or change LLM_MODEL."
            )
        return cfg.LLM_MODEL
    if spec.provider is LLMProvider.ollama and models.allows(cfg.OLLAMA_MODEL):
        return cfg.OLLAMA_MODEL
    if models.first:
        return models.first
    if is_default:
        raise LLMConfigError(f"{spec.setting('MODELS')}=* lists no model to default to. Set LLM_MODEL.")
    return None


def _model_hint(cfg) -> str:
    """What to suggest for an empty <PREFIX>_MODELS of the default provider."""
    return cfg.LLM_MODEL or "<model name>"


def is_local_url(url: str) -> bool:
    """True for localhost, private IPs, and bare names like Docker service names."""
    host = urlparse(url).hostname or ""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return (
            host in {"localhost", "host.docker.internal"}
            or "." not in host
            or host.endswith((".local", ".internal", ".lan"))
        )
    return ip.is_loopback or ip.is_private


def _check_url(name: str, url: str) -> str:
    try:
        parsed = urlparse(url)
    except ValueError:
        raise LLMConfigError(f"{name} is not a valid URL. It should look like http://host:port.") from None
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise LLMConfigError(f"{name}={url!r} is not a valid URL. It should look like http://host:port.")
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
