from pydantic import BaseModel

class TemplateCreate(BaseModel):
    name: str
    pdf_path: str
    fields: dict

class TemplateResponse(BaseModel):
    id: int
    name: str
    pdf_path: str
    fields: dict

    class Config:
        from_attributes = True