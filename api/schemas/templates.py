from pydantic import BaseModel, ConfigDict

class TemplateCreate(BaseModel):
    name: str
    pdf_path: str
    fields: dict

class TemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    pdf_path: str
    fields: dict