from pydantic import BaseModel


class ModelInfo(BaseModel):
    name: str
    size_gb: float
    quantization: str | None = None
    loaded: bool


class CurrentLoad(BaseModel):
    active_requests: int
    queued_requests: int


class ComponentHealth(BaseModel):
    status: str
    response_time_ms: int | None = None
    detail: str | None = None
    model_loaded: str | None = None
    ollama_version: str | None = None
    models_available: list[ModelInfo] | None = None
    current_load: CurrentLoad | None = None
    disk_free_gb: float | None = None


class HealthComponents(BaseModel):
    database: ComponentHealth
    ollama: ComponentHealth
    whisper: ComponentHealth
    storage: ComponentHealth


class HealthStatus(BaseModel):
    status: str
    version: str
    uptime_seconds: int | None = None
    components: HealthComponents | None = None


class SchemaVersion(BaseModel):
    version: str
    released_at: str
    changelog: str | None = None
    breaking_changes: bool | None = None
