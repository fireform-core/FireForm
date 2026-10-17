from pydantic import BaseModel

from app.api.schemas.enums import HealthState, LLMProvider


class ModelInfo(BaseModel):
    name: str
    size_gb: float | None = None
    quantization: str | None = None
    loaded: bool | None = None


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


class SchemaVersion(BaseModel):
    version: str
    released_at: str
    changelog: str | None = None
    breaking_changes: bool | None = None
