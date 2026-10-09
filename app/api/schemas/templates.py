from pydantic import BaseModel, ConfigDict

class TemplateCreate(BaseModel):
    name: str
    description: str = ""
    pdf_path: str
    fields: dict = {}


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

    model_config = ConfigDict(from_attributes=True)


class ExtractedField(BaseModel):
    name: str
    description: str = ""
    type: str = "string"


class TemplateUploadResponse(BaseModel):
    filename: str
    pdf_path: str
    field_count: int | None = None
    fields: list[ExtractedField] = []
    schema_data: dict | None = None
    tables: list[dict] | None = None
