from pydantic import BaseModel, Field


class TemplateCreate(BaseModel):
    name: str
    description: str = Field(
        description=(
            "What this form is for, in one or two plain sentences (for example: "
            "'Wildfire incident communications plan for a Type 1 ICS incident'). "
            "Sent to the local LLM with every fill to give it context on the form's "
            "purpose, so ambiguous narrative wording is resolved in the right context. "
            "Describe the form's purpose and scope - not the incident it will be used "
            "for, which comes from the narrative - and keep it free of personal data. "
            "Required on create; send an empty string if the template needs no context."
        )
    )
    pdf_path: str
    fields: dict


class MakeFillableRequest(BaseModel):
    pdf_path: str


class MakeFillableResponse(BaseModel):
    pdf_path: str
    field_count: int | None = None


class TemplateResponse(BaseModel):
    id: int
    name: str
    description: str
    pdf_path: str
    fields: dict
    field_count: int | None = None

    class Config:
        from_attributes = True


class ExtractedField(BaseModel):
    name: str
    description: str
    type: str


class TemplateUploadResponse(BaseModel):
    filename: str
    pdf_path: str
    field_count: int | None = None
    fields: list[ExtractedField] = []
