from pydantic import BaseModel


class TemplateUpdate(BaseModel):
    name: str | None = None
    fields: dict | None = None
    pdf_path: str | None = None


class TemplateResponse(BaseModel):
    id: int
    name: str
    pdf_path: str
    fields: dict

    class Config:
        from_attributes = True