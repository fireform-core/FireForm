from pydantic import BaseModel, field_validator

class FormFill(BaseModel):
    template_id: int
    input_text: str
    # Optional Ollama model override for this fill; falls back to OLLAMA_MODEL.
    # Not persisted (no DB column) — excluded before building FormSubmission.
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