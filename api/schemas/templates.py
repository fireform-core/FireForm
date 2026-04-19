from pydantic import BaseModel, Field, field_validator


class TemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    pdf_path: str = Field(..., min_length=1)
    fields: dict

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        stripped = v.strip()
        if not stripped:
            raise ValueError("Template name cannot be empty or only whitespace")
        return stripped


class TemplateResponse(BaseModel):
    id: int
    name: str
    pdf_path: str
    fields: dict

    model_config = {"from_attributes": True}


class TemplateUploadResponse(BaseModel):
    filename: str
    pdf_path: str