from pydantic import BaseModel, Field

class FormFill(BaseModel):
    template_id: int
    input_text: str
    retry_input_texts: list[str] = Field(default_factory=list)
    max_retry_rounds: int = Field(default=1, ge=0, le=5)


class FormFillResponse(BaseModel):
    id: int
    template_id: int
    input_text: str
    output_pdf_path: str | None = None
    status: str
    required_completion_pct: int
    completed_required_fields: list[str] = Field(default_factory=list)
    missing_required_fields: list[str] = Field(default_factory=list)
    attempts_used: int
    retry_prompt: str | None = None

    class Config:
        from_attributes = True