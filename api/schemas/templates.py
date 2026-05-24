from pydantic import BaseModel

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
    id: int
    name: str
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
