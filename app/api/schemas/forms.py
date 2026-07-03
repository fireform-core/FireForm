from pydantic import BaseModel, field_validator


class FormFill(BaseModel):
    template_id: int
    input_text: str
    model: str | None = None

    @field_validator("input_text")
    def validate_input_text(cls, value):
        if not value or not value.strip():
            raise ValueError("Input text cannot be empty")
        return value


class FormFillResponse(BaseModel):
    id: int
    template_id: int
    input_text: str
    output_pdf_path: str

    class Config:
        from_attributes = True


class TranscriptionResponse(BaseModel):
    text: str


class ModelsResponse(BaseModel):
    models: list[str]
    default: str


class AsyncFormFill(BaseModel):
    template_ids: list[int]
    input_text: str
    model: str | None = None

    @field_validator("input_text")
    def validate_input_text(cls, value):
        if not value or not value.strip():
            raise ValueError("Input text cannot be empty")
        return value

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


class ModelPullRequest(BaseModel):
    model: str