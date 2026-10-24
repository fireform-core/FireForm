"""Runtime credentials for FireForm's local, single-user installation."""

import copy
import logging
import os
import threading
import time
from dataclasses import replace
from types import SimpleNamespace
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from sqlmodel import Session, select

from app.api.schemas.enums import LLMProvider
from app.core import config
from app.models import LLMManualModel, LLMProviderCredential, LLMRuntimeConfig
from app.services.llm.errors import LLMSecretKeyError
from app.services.llm.registry import LLMRegistry
from app.services.llm.settings import load_settings

logger = logging.getLogger(__name__)

EDITABLE_PROVIDERS = frozenset({
    LLMProvider.openai,
    LLMProvider.gemini,
    LLMProvider.anthropic,
    LLMProvider.custom,
})
_cache_lock = threading.Lock()
_credential_state_lock = threading.Lock()
_cached_registry: LLMRegistry | None = None
_cached_fingerprint: tuple | None = None
_cache_checked_at = 0.0
_REGISTRY_CHECK_SECONDS = 3.0
_BASE_CONFIG_FINGERPRINT = ("base-config",)
_invalid_credentials: set[str] = set()
_warned_credential_errors: dict[str, str] = {}


def _fernet(*, create: bool = False) -> Fernet:
    if config.LLM_SECRET_KEY:
        try:
            key = config.LLM_SECRET_KEY.encode("ascii")
        except UnicodeEncodeError:
            raise LLMSecretKeyError("LLM master key is unavailable.") from None
        return _build_fernet(key)

    key_file = Path(config.LLM_SECRET_KEY_FILE)
    if create:
        key = _read_or_create_key_file(key_file)
    else:
        try:
            key = key_file.read_bytes()
        except OSError:
            raise LLMSecretKeyError("LLM master key is unavailable.") from None
    return _build_fernet(key)


def _build_fernet(key: bytes) -> Fernet:
    try:
        return Fernet(key.strip())
    except (TypeError, ValueError):
        raise LLMSecretKeyError("LLM master key is unavailable.") from None


def _read_or_create_key_file(path: Path) -> bytes:
    try:
        key = path.read_bytes()
        if key:
            return key
    except FileNotFoundError:
        pass
    except OSError:
        raise LLMSecretKeyError("LLM master key is unavailable.") from None

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return _read_key_after_create_race(path)
    except OSError:
        raise LLMSecretKeyError("LLM master key is unavailable.") from None

    key = Fernet.generate_key()
    try:
        with os.fdopen(descriptor, "wb") as key_file:
            key_file.write(key)
            key_file.flush()
            os.fsync(key_file.fileno())
    except OSError:
        try:
            path.unlink()
        except OSError:
            pass
        raise LLMSecretKeyError("LLM master key is unavailable.") from None
    return key


def _read_key_after_create_race(path: Path) -> bytes:
    for attempt in range(10):
        try:
            key = path.read_bytes()
        except OSError:
            key = b""
        if key:
            return key
        if attempt < 9:
            time.sleep(0.01)
    raise LLMSecretKeyError("LLM master key is unavailable.")


def encrypt_api_key(value: str) -> str:
    return _fernet(create=True).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_api_key(value: str, provider: str) -> str | None:
    try:
        decrypted = _fernet().decrypt(value.encode("ascii")).decode("utf-8")
        with _credential_state_lock:
            _invalid_credentials.discard(provider)
            _warned_credential_errors.pop(provider, None)
        return decrypted
    except LLMSecretKeyError:
        with _credential_state_lock:
            _invalid_credentials.add(provider)
        _warn_credential_error(provider, value, "LLM_SECRET_KEY is unavailable")
    except (InvalidToken, UnicodeDecodeError, ValueError):
        with _credential_state_lock:
            _invalid_credentials.add(provider)
        _warn_credential_error(provider, value, "ignoring the saved credential")
    return None


def _warn_credential_error(provider: str, encrypted_value: str, reason: str) -> None:
    with _credential_state_lock:
        if _warned_credential_errors.get(provider) == encrypted_value:
            return
        _warned_credential_errors[provider] = encrypted_value
    logger.warning("Stored API key for %s cannot be decrypted; %s.", provider, reason)


def has_decryptable_credential(provider: str) -> bool:
    with _credential_state_lock:
        return provider not in _invalid_credentials


def validate_provider(provider: LLMProvider) -> None:
    if provider not in EDITABLE_PROVIDERS:
        from app.services.llm.errors import LLMNotAvailableError

        raise LLMNotAvailableError("Only OpenAI, Gemini, Anthropic, and custom providers can be configured here.")


def registry_for_candidate(
    session: Session,
    provider: LLMProvider,
    *,
    api_key: str | None,
    base_url: str | None = None,
    structured_output: bool | None = None,
    manual_model: str | None = None,
) -> LLMRegistry:
    credentials = {row.provider: row for row in session.exec(select(LLMProviderCredential)).all()}
    manual_models = session.exec(select(LLMManualModel)).all()
    runtime_config = session.get(LLMRuntimeConfig, 1)
    override = {
        "api_key": api_key,
        "base_url": base_url,
        "structured_output": structured_output,
    }
    return _build_registry(
        credentials,
        manual_models,
        runtime_config.allow_external if runtime_config else False,
        candidate=(provider, override, manual_model),
    )


def effective_registry(session: Session) -> LLMRegistry:
    """Return a process-local registry rebuilt when persisted provider state changes."""
    global _cache_checked_at, _cached_registry, _cached_fingerprint
    with _cache_lock:
        now = time.monotonic()
        if now - _cache_checked_at < _REGISTRY_CHECK_SECONDS:
            if _cached_fingerprint == _BASE_CONFIG_FINGERPRINT:
                from app.services import llm

                return llm.get_registry()
            if _cached_registry is not None:
                return _cached_registry

        credentials = session.exec(select(LLMProviderCredential)).all()
        manual_models = session.exec(select(LLMManualModel)).all()
        runtime_config = session.get(LLMRuntimeConfig, 1)
        allow_external = runtime_config.allow_external if runtime_config else False
        if not credentials and not manual_models and not allow_external:
            from app.services import llm

            _cached_registry = None
            _cached_fingerprint = _BASE_CONFIG_FINGERPRINT
            _cache_checked_at = now
            return llm.get_registry()

        fingerprint = (
            tuple(sorted((row.provider, row.updated_at, row.key_hint, row.base_url, row.structured_output) for row in credentials)),
            tuple(sorted((row.provider, row.model, row.created_at) for row in manual_models)),
            runtime_config.updated_at if runtime_config else None,
            allow_external,
        )
        if fingerprint == _cached_fingerprint and _cached_registry is not None:
            _cache_checked_at = now
            return _cached_registry

        _cached_registry = _build_registry(
            {row.provider: row for row in credentials},
            manual_models,
            allow_external,
        )
        _cached_fingerprint = fingerprint
        _cache_checked_at = now
        return _cached_registry


def invalidate_registry_cache() -> None:
    global _cache_checked_at, _cached_registry, _cached_fingerprint
    with _cache_lock:
        _cached_registry = None
        _cached_fingerprint = None
        _cache_checked_at = 0.0


def _build_registry(
    credentials: dict[str, LLMProviderCredential],
    manual_models: list[LLMManualModel],
    allow_external: bool,
    candidate: tuple[LLMProvider, dict, str | None] | None = None,
) -> LLMRegistry:
    provider_env = copy.deepcopy(config.LLM_PROVIDER_ENV)
    runtime_allow_external = allow_external or str(config.LLM_ALLOW_EXTERNAL).lower() in {"true", "1", "yes"}
    manual_by_provider: dict[LLMProvider, list[str]] = {}
    unavailable_credentials: set[str] = set()

    for record in manual_models:
        try:
            provider = LLMProvider(record.provider)
        except ValueError:
            continue
        manual_by_provider.setdefault(provider, []).append(record.model)

    for provider_name, record in credentials.items():
        try:
            provider = LLMProvider(provider_name)
        except ValueError:
            continue
        provider_settings = provider_env[provider.value]
        api_key = decrypt_api_key(record.api_key_encrypted, provider.value) if record.api_key_encrypted else None
        if record.api_key_encrypted and not api_key:
            unavailable_credentials.add(provider.value)
        if api_key:
            provider_settings["API_KEY"] = api_key
        if provider is LLMProvider.custom and record.base_url:
            provider_settings["BASE_URL"] = record.base_url
        if provider is LLMProvider.custom and record.structured_output is not None:
            provider_settings["STRUCTURED_OUTPUT"] = str(record.structured_output).lower()
        if not provider_settings.get("MODELS") and (api_key or (provider is LLMProvider.custom and record.base_url)):
            provider_settings["MODELS"] = "*"

    if candidate:
        provider, override, extra_model = candidate
        provider_settings = provider_env[provider.value]
        if override["api_key"] is not None:
            provider_settings["API_KEY"] = override["api_key"]
        if provider is LLMProvider.custom and override["base_url"] is not None:
            provider_settings["BASE_URL"] = override["base_url"]
        if provider is LLMProvider.custom and override["structured_output"] is not None:
            provider_settings["STRUCTURED_OUTPUT"] = str(override["structured_output"]).lower()
        if not provider_settings.get("MODELS"):
            provider_settings["MODELS"] = "*"
        if extra_model:
            manual_by_provider.setdefault(provider, []).append(extra_model)

    for provider, names in manual_by_provider.items():
        provider_settings = provider_env[provider.value]
        configured = provider_settings.get("MODELS", "")
        if configured and configured.strip() != "*":
            provider_settings["MODELS"] = ",".join(dict.fromkeys([*configured.split(","), *names]))
        elif not configured:
            provider_settings["MODELS"] = ",".join(dict.fromkeys(names))

    effective_config = SimpleNamespace(**vars(config))
    effective_config.LLM_PROVIDER_ENV = provider_env
    effective_config.LLM_ALLOW_EXTERNAL = "true" if runtime_allow_external else "false"
    if (
        config.LLM_PROVIDER in unavailable_credentials
        and not provider_env[config.LLM_PROVIDER].get("API_KEY")
        and provider_env[LLMProvider.ollama.value].get("MODELS")
    ):
        effective_config.LLM_PROVIDER = LLMProvider.ollama.value
        effective_config.LLM_MODEL = ""
    settings = load_settings(effective_config)
    for provider, names in manual_by_provider.items():
        if provider in settings.providers:
            settings.providers[provider] = replace(
                settings.providers[provider],
                manual_models=tuple(dict.fromkeys(names)),
            )
    return LLMRegistry.from_settings(settings)
