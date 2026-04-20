from pydantic import BaseModel, field_validator

class FormFill(BaseModel):
    template_id: int
    input_text: str

    @field_validator("input_text")
    @classmethod
    def validate_input_text(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("input_text cannot be empty or whitespace.")
        if len(v) > 10_000:
            raise ValueError("input_text exceeds maximum length of 10,000 characters.")
        return v


class FormFillResponse(BaseModel):
    id: int
    template_id: int
    input_text: str
    output_pdf_path: str

    class Config:
        from_attributes = True