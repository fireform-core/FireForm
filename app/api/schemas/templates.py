from pydantic import BaseModel, ConfigDict


class TemplateCreate(BaseModel):
    name: str
    pdf_path: str
    fields: dict


class MakeFillableRequest(BaseModel):
    pdf_path: str


class MakeFillableResponse(BaseModel):
    pdf_path: str
    field_count: int | None = None

class TemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    pdf_path: str
    fields: dict
    field_count: int | None = None


class ExtractedField(BaseModel):
    name: str
    description: str
    type: str


class TemplateUploadResponse(BaseModel):
    filename: str
    pdf_path: str
    field_count: int | None = None
    fields: list[ExtractedField] = []
