from pydantic import BaseModel, Field, field_validator


class FormFill(BaseModel):
    template_id: int
    input_text: str = Field(..., min_length=1, max_length=50000)

    @field_validator("input_text")
    @classmethod
    def validate_input_text(cls, v):
        stripped = v.strip()
        if not stripped:
            raise ValueError("Input text cannot be empty or only whitespace")
        return stripped


class FormFillResponse(BaseModel):
    id: int
    template_id: int
    input_text: str
    output_pdf_path: str

    model_config = {"from_attributes": True}