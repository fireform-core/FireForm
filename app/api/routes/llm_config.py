from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends
from pydantic import SecretStr
from sqlmodel import Session, select

from app.api.deps import get_db
from app.api.schemas.enums import LLMProvider
from app.api.schemas.system import (
    LLMExternalConsent,
    LLMExternalConsentRequest,
    LLMManualModelRequest,
    LLMManualModelResult,
    LLMProviderCredentialList,
    LLMProviderCredentialRequest,
    LLMProviderCredentialStatus,
    LLMProviderValidationRequest,
    LLMProviderValidationResult,
    ModelInfo,
)
from app.core import config
from app.models import LLMManualModel, LLMProviderCredential, LLMRuntimeConfig
from app.services import llm
from app.services.llm.errors import (
    LLMError,
    LLMExternalConsentError,
    LLMNotAvailableError,
)
from app.services.llm.settings import is_local_url
from app.services.llm.specs import SPECS
from app.services.llm.user_config import (
    EDITABLE_PROVIDERS,
    decrypt_api_key,
    effective_registry,
    encrypt_api_key,
    invalidate_registry_cache,
    has_decryptable_credential,
    registry_for_candidate,
    validate_provider,
)

router = APIRouter(prefix="/system/llm", tags=["system"])
_EXTERNAL_ENV_ALLOWED = str(config.LLM_ALLOW_EXTERNAL).lower() in {"true", "1", "yes"}


@router.get("/providers/config", response_model=LLMProviderCredentialList)
def get_provider_configs(db: Session = Depends(get_db)):
    credentials = {row.provider: row for row in db.exec(select(LLMProviderCredential)).all()}
    try:
        registry = effective_registry(db)
        enabled = set(registry.providers)
    except LLMError:
        enabled = set()

    statuses = []
    for provider in sorted(EDITABLE_PROVIDERS, key=lambda item: item.value):
        spec = SPECS[provider]
        record = credentials.get(provider.value)
        env = config.LLM_PROVIDER_ENV[provider.value]
        env_key = env.get("API_KEY", "")
        ui_key = bool(
            record and record.api_key_encrypted and has_decryptable_credential(provider.value)
        )
        ui_custom_url = bool(provider is LLMProvider.custom and record and record.base_url)
        source = "ui" if ui_key or ui_custom_url else "env" if env_key or env.get("BASE_URL") else "none"
        base_url = (record.base_url if ui_custom_url else None) or env.get("BASE_URL") or spec.default_base_url
        key_hint = record.key_hint if ui_key else env_key[-4:] if env_key else None
        statuses.append(
            LLMProviderCredentialStatus(
                provider=provider,
                configured=source != "none",
                source=source,
                key_hint=key_hint,
                enabled=provider in enabled,
                external=_is_external_url(base_url) if base_url else False,
                credential_status=(
                    "available" if has_decryptable_credential(provider.value) else "unavailable"
                ) if record and record.api_key_encrypted else None,
                base_url=_display_base_url(base_url) if provider is LLMProvider.custom else None,
                structured_output=(
                    record.structured_output
                    if provider is LLMProvider.custom and record and record.structured_output is not None
                    else None
                ),
            )
        )
    return LLMProviderCredentialList(providers=statuses)


@router.put("/providers/config/{provider}", response_model=LLMProviderCredentialStatus)
def save_provider_config(
    provider: LLMProvider,
    body: LLMProviderCredentialRequest,
    db: Session = Depends(get_db),
):
    validate_provider(provider)
    record = db.exec(
        select(LLMProviderCredential).where(LLMProviderCredential.provider == provider.value)
    ).first()
    env = config.LLM_PROVIDER_ENV[provider.value]

    if provider is not LLMProvider.custom and body.structured_output is not None:
        raise LLMNotAvailableError("Only the custom provider accepts a structured_output override.")
    if provider is not LLMProvider.custom and body.base_url is not None:
        raise LLMNotAvailableError("Only the custom provider accepts a configurable base URL.")

    base_url = body.base_url if provider is LLMProvider.custom and body.base_url is not None else None
    if provider is LLMProvider.custom:
        base_url = base_url or (record.base_url if record else None) or env.get("BASE_URL") or None
        if not base_url:
            raise LLMNotAvailableError("CUSTOM_BASE_URL is required.")
        base_url = _validate_custom_url(base_url)

    api_key_was_provided = "api_key" in body.model_fields_set and body.api_key is not None
    api_key = _provided_secret(body.api_key) if api_key_was_provided else None
    if not api_key_was_provided and record and record.api_key_encrypted:
        api_key = decrypt_api_key(record.api_key_encrypted, provider.value)
    if not api_key:
        api_key = env.get("API_KEY") or None
    if SPECS[provider].needs_key and not api_key:
        raise LLMNotAvailableError(f"{provider.value} requires an API key.")

    _require_external_consent(db, provider, base_url or env.get("BASE_URL") or SPECS[provider].default_base_url)

    if record is None:
        record = LLMProviderCredential(provider=provider.value)
    if api_key_was_provided:
        secret = _provided_secret(body.api_key)
        record.api_key_encrypted = encrypt_api_key(secret) if secret else None
        record.key_hint = secret[-4:] if secret else None
    if provider is LLMProvider.custom:
        record.base_url = base_url
        if body.structured_output is not None:
            record.structured_output = body.structured_output
    record.updated_at = datetime.now(timezone.utc)
    db.add(record)
    db.commit()
    db.refresh(record)
    invalidate_registry_cache()
    return next(status for status in get_provider_configs(db).providers if status.provider is provider)


@router.delete("/providers/config/{provider}")
def delete_provider_config(provider: LLMProvider, db: Session = Depends(get_db)):
    validate_provider(provider)
    record = db.exec(
        select(LLMProviderCredential).where(LLMProviderCredential.provider == provider.value)
    ).first()
    if record:
        db.delete(record)
    for manual in db.exec(select(LLMManualModel).where(LLMManualModel.provider == provider.value)).all():
        db.delete(manual)
    db.commit()
    invalidate_registry_cache()
    return {"status": "success"}


@router.get("/external-consent", response_model=LLMExternalConsent)
def get_external_consent(db: Session = Depends(get_db)):
    record = db.get(LLMRuntimeConfig, 1)
    if _EXTERNAL_ENV_ALLOWED:
        return LLMExternalConsent(allow_external=True, source="env")
    if record and record.allow_external:
        return LLMExternalConsent(allow_external=True, source="ui")
    return LLMExternalConsent(allow_external=False, source="none")


@router.put("/external-consent", response_model=LLMExternalConsent)
def set_external_consent(body: LLMExternalConsentRequest, db: Session = Depends(get_db)):
    record = db.get(LLMRuntimeConfig, 1)
    if record is None:
        record = LLMRuntimeConfig(id=1)
    record.allow_external = body.allow_external
    record.updated_at = datetime.now(timezone.utc)
    db.add(record)
    db.commit()
    invalidate_registry_cache()
    return get_external_consent(db)


@router.post("/providers/config/{provider}/validate", response_model=LLMProviderValidationResult)
def validate_provider_config(
    provider: LLMProvider,
    body: LLMProviderValidationRequest,
    db: Session = Depends(get_db),
):
    validate_provider(provider)
    if provider is not LLMProvider.custom and body.structured_output is not None:
        return LLMProviderValidationResult(
            provider=provider,
            ok=False,
            detail="Only the custom provider accepts a structured_output override.",
            error_code="LLM_CONFIG_ERROR",
        )
    api_key = _provided_secret(body.api_key)
    if SPECS[provider].needs_key and not api_key:
        return LLMProviderValidationResult(
            provider=provider,
            ok=False,
            detail="Enter an API key to validate the provider configuration.",
            error_code="LLM_AUTH_FAILED",
        )
    base_url = body.base_url
    if provider is LLMProvider.custom:
        if not base_url:
            return LLMProviderValidationResult(
                provider=provider,
                ok=False,
                detail="CUSTOM_BASE_URL is required.",
                error_code="LLM_CONFIG_ERROR",
            )
        try:
            base_url = _validate_custom_url(base_url)
        except LLMError as exc:
            return LLMProviderValidationResult(provider=provider, ok=False, detail=exc.message,
                                               error_code=exc.error_code)
    elif base_url is not None:
        return LLMProviderValidationResult(
            provider=provider,
            ok=False,
            detail="Only the custom provider accepts a configurable base URL.",
            error_code="LLM_CONFIG_ERROR",
        )

    try:
        _require_external_consent(
            db,
            provider,
            base_url or config.LLM_PROVIDER_ENV[provider.value].get("BASE_URL") or SPECS[provider].default_base_url,
        )
        registry = registry_for_candidate(
            db,
            provider,
            api_key=api_key,
            base_url=base_url,
            structured_output=body.structured_output,
        )
        models = registry.client(provider).list_models()
        return LLMProviderValidationResult(
            provider=provider, ok=True, models=[ModelInfo.model_validate(model) for model in models]
        )
    except LLMError as exc:
        detail = _redact(exc.message, api_key)
        if provider is LLMProvider.custom and "has no model list" in detail:
            detail = "This server does not expose a model list. Validate a model ID manually."
        return LLMProviderValidationResult(
            provider=provider, ok=False, detail=detail, error_code=exc.error_code
        )


@router.post("/providers/config/{provider}/models", response_model=LLMManualModelResult)
def validate_and_add_manual_model(
    provider: LLMProvider,
    body: LLMManualModelRequest,
    db: Session = Depends(get_db),
):
    validate_provider(provider)
    try:
        existing_config = db.exec(
            select(LLMProviderCredential).where(LLMProviderCredential.provider == provider.value)
        ).first()
        env = config.LLM_PROVIDER_ENV[provider.value]
        base_url = (
            existing_config.base_url if provider is LLMProvider.custom and existing_config else None
        ) or env.get("BASE_URL") or SPECS[provider].default_base_url
        _require_external_consent(db, provider, base_url)
        candidate = registry_for_candidate(
            db,
            provider,
            api_key=None,
            manual_model=body.model,
        )
        check = llm.ModelValidator(candidate).probe(provider, body.model)
    except LLMError as exc:
        return LLMManualModelResult(
            provider=provider, model=body.model, ok=False, detail=exc.message, error_code=exc.error_code
        )
    if not check.ok:
        return LLMManualModelResult(
            provider=provider, model=body.model, ok=False, detail=check.detail, error_code=check.error_code
        )
    existing = db.exec(
        select(LLMManualModel).where(
            LLMManualModel.provider == provider.value,
            LLMManualModel.model == body.model,
        )
    ).first()
    if existing is None:
        db.add(LLMManualModel(provider=provider.value, model=body.model))
        db.commit()
    invalidate_registry_cache()
    return LLMManualModelResult(provider=provider, model=body.model, ok=True)


@router.delete("/providers/config/{provider}/models")
def delete_manual_model(
    provider: LLMProvider,
    body: LLMManualModelRequest,
    db: Session = Depends(get_db),
):
    validate_provider(provider)
    existing = db.exec(
        select(LLMManualModel).where(
            LLMManualModel.provider == provider.value,
            LLMManualModel.model == body.model,
        )
    ).first()
    if existing:
        db.delete(existing)
        db.commit()
        invalidate_registry_cache()
    return {"status": "success"}


def _provided_secret(value: SecretStr | None) -> str:
    return value.get_secret_value().strip() if value else ""


def _validate_custom_url(value: str) -> str:
    try:
        parsed = urlparse(value)
    except ValueError:
        raise LLMNotAvailableError("CUSTOM_BASE_URL must be an HTTP or HTTPS URL with a hostname.") from None
    if parsed.username is not None or parsed.password is not None:
        raise LLMNotAvailableError("CUSTOM_BASE_URL must not include embedded credentials.")
    if parsed.query or parsed.fragment:
        raise LLMNotAvailableError("CUSTOM_BASE_URL must not include query parameters or a fragment.")
    from app.services.llm.settings import _check_url
    from app.services.llm.errors import LLMConfigError

    try:
        return _check_url("CUSTOM_BASE_URL", value)
    except LLMConfigError:
        raise LLMNotAvailableError("CUSTOM_BASE_URL must be an HTTP or HTTPS URL with a hostname.") from None


def _display_base_url(value: str) -> str:
    try:
        parsed = urlparse(value)
        host = parsed.hostname or ""
        port = parsed.port
    except ValueError:
        return "Invalid custom URL"
    if port:
        host = f"{host}:{port}"
    return f"{parsed.scheme}://{host}{parsed.path}"


def _is_external_url(value: str) -> bool:
    try:
        return not is_local_url(value)
    except ValueError:
        return True


def _require_external_consent(db: Session, provider: LLMProvider, base_url: str) -> None:
    record = db.get(LLMRuntimeConfig, 1)
    if _is_external_url(base_url) and not _EXTERNAL_ENV_ALLOWED and not (record and record.allow_external):
        raise LLMExternalConsentError(
            "Allow external processing before configuring a provider outside the local network."
        )


def _redact(message: str, secret: object) -> str:
    if isinstance(secret, str) and len(secret) >= 8 and secret != "not-needed":
        return message.replace(secret, "[redacted]")
    return message
