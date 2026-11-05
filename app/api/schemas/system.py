import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.api.schemas.enums import HealthState, LLMProvider

_MODEL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-/:]*$")


def validate_model_name(value: str | None) -> str:
    if value is None:
        raise ValueError("model name cannot be empty")
    value = value.strip()
    if not value:
        raise ValueError("model name cannot be empty")
    if len(value) > 128:
        raise ValueError("model name must be at most 128 characters")
    if not _MODEL_NAME_PATTERN.fullmatch(value):
        raise ValueError("model name contains invalid characters")
    return value


class ModelInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    size_gb: float | None = None
    quantization: str | None = None
    loaded: bool | None = None
    installed: bool | None = None
    manual: bool | None = None


class DownloadableModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    installed: bool = False


class CurrentLoad(BaseModel):
    active_requests: int
    queued_requests: int


class ComponentHealth(BaseModel):
    status: HealthState
    response_time_ms: int | None = None
    detail: str | None = None
    provider: LLMProvider | None = None  # llm component only
    model_loaded: str | None = None
    provider_version: str | None = None
    models_available: list[ModelInfo] | None = None
    current_load: CurrentLoad | None = None
    disk_free_gb: float | None = None


class HealthComponents(BaseModel):
    database: ComponentHealth
    llm: ComponentHealth
    whisper: ComponentHealth
    storage: ComponentHealth


class HealthStatus(BaseModel):
    status: HealthState
    version: str
    uptime_seconds: int | None = None
    components: HealthComponents | None = None


class LLMModelChoice(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider: LLMProvider
    model: str


class LLMProviderModels(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider: LLMProvider
    available: bool
    default_model: str | None = None
    detail: str | None = None
    error_code: str | None = None
    models: list[ModelInfo]
    downloadable: list[DownloadableModel] | None = None


class LLMModels(BaseModel):
    default: LLMModelChoice
    providers: list[LLMProviderModels]


class LLMPullRequest(BaseModel):
    model: str
    provider: str | None = "ollama"

    @field_validator("model")
    @classmethod
    def _validate_model_name(cls, value: str) -> str:
        return validate_model_name(value)


class LLMModelDeleteRequest(BaseModel):
    model: str
    provider: str | None = "ollama"

    @field_validator("model")
    @classmethod
    def _validate_model_name(cls, value: str) -> str:
        return validate_model_name(value)


class LLMModelDeleteResult(BaseModel):
    model: str
    deleted: bool


class LLMTestRequest(BaseModel):
    provider: LLMProvider | None = None
    model: str | None = None


class LLMTestResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider: LLMProvider
    model: str
    ok: bool
    latency_ms: int | None = None
    detail: str | None = None
    error_code: str | None = None


class LLMProviderCredentialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: SecretStr | None = None
    base_url: str | None = None
    structured_output: bool | None = None


class LLMProviderCredentialStatus(BaseModel):
    provider: LLMProvider
    configured: bool
    source: Literal["env", "ui", "none"]
    key_hint: str | None = None
    enabled: bool
    external: bool
    credential_status: Literal["available", "unavailable"] | None = None
    base_url: str | None = None
    structured_output: bool | None = None


class LLMProviderCredentialList(BaseModel):
    providers: list[LLMProviderCredentialStatus]


class LLMExternalConsent(BaseModel):
    allow_external: bool
    source: Literal["env", "ui", "none"]


class LLMExternalConsentRequest(BaseModel):
    allow_external: bool


class LLMProviderValidationRequest(LLMProviderCredentialRequest):
    pass


class LLMProviderValidationResult(BaseModel):
    provider: LLMProvider
    ok: bool
    models: list[ModelInfo] = Field(default_factory=list)
    detail: str | None = None
    error_code: str | None = None


class LLMManualModelRequest(BaseModel):
    model: str

    @field_validator("model")
    @classmethod
    def _validate_model_name(cls, value: str) -> str:
        return validate_model_name(value)


class LLMManualModelResult(BaseModel):
    provider: LLMProvider
    model: str
    ok: bool
    detail: str | None = None
    error_code: str | None = None


class SchemaVersion(BaseModel):
    version: str
    released_at: str
    changelog: str | None = None
    breaking_changes: bool | None = None
