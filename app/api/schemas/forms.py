from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


class FormFill(BaseModel):
    template_id: int
    input_text: str | None = None
    input_id: UUID | None = None
    model: str | None = None


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
    job_type: str
    status: str
    progress_percent: int = 0
    result_url: str | None = None
    error: dict | None = None
    created_at: str | None = None
    updated_at: str | None = None

    class Config:
        from_attributes = True


class AsyncJobSubmitResponse(BaseModel):
    job_id: str
    status: str
    poll_url: str

    class Config:
        from_attributes = True


class AsyncFormFillResponse(BaseModel):
    jobs: list[AsyncJobSubmitResponse]