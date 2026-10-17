import re
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.api.schemas.enums import JobStatus, JobType

_MODEL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-/:]*$")


def validate_model_name(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        raise ValueError("model name cannot be empty")
    if len(value) > 128:
        raise ValueError("model name must be at most 128 characters")
    if not _MODEL_NAME_PATTERN.fullmatch(value):
        raise ValueError("model name contains invalid characters")
    return value


class FormFill(BaseModel):
    template_id: int
    input_text: str | None = None
    input_id: UUID | None = None
    model: str | None = None

    @field_validator("model")
    @classmethod
    def _validate_model_name(cls, value: str | None) -> str | None:
        return validate_model_name(value)


class FormFillResponse(BaseModel):
    id: int
    template_id: int
    input_text: str
    output_pdf_path: str
    values: dict | None = None

    model_config = ConfigDict(from_attributes=True)


class TranscriptionResponse(BaseModel):
    text: str


class ModelInfo(BaseModel):
    name: str
    installed: bool
    recommended: bool


class ModelsResponse(BaseModel):
    current_model: str
    models: list[ModelInfo]


class ModelPullRequest(BaseModel):
    model: str

    @field_validator("model")
    @classmethod
    def _validate_model_name(cls, value: str) -> str:
        return validate_model_name(value) or ""


class AsyncFormFill(BaseModel):
    template_ids: list[int]
    input_id: UUID
    model: str | None = None

    @field_validator("template_ids")
    def validate_template_ids(cls, value):
        if not value:
            raise ValueError("template_ids cannot be empty")
        return value


class JobResponse(BaseModel):
    job_id: str
    job_type: JobType
    status: JobStatus
    progress_percent: int = 0
    result_url: str | None = None
    error: dict | None = None
    created_at: str | None = None
    updated_at: str | None = None

    class Config:
        from_attributes = True


class AsyncJobSubmitResponse(BaseModel):
    job_id: str
    status: JobStatus
    poll_url: str

    class Config:
        from_attributes = True


class AsyncFormFillResponse(BaseModel):
    jobs: list[AsyncJobSubmitResponse]
    # Present only on a partial failure (HTTP 207): lists the job IDs that were
    # successfully queued before the broker became unreachable.
    error: str | None = None