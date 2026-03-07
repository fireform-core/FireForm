from pydantic import BaseModel
from typing import Optional

class FormFill(BaseModel):
    template_id: int
    input_text: str

class FormFeedback(BaseModel):
    input_text: str

class FormFillResponse(BaseModel):
    id: int
    template_id: int
    input_text: str
    status: str
    output_pdf_path: Optional[str] = None
    extracted_data: dict = {}
    missing_fields: list = []

    class Config:
        from_attributes = True