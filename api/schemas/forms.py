from pydantic import BaseModel
from typing import Optional

class FormFill(BaseModel):
    template_id: int
    input_text: str


class FormFillResponse(BaseModel):
    id: int
    template_id: int
    input_text: str
    output_pdf_path: str
    # BCP-47 code of the detected source language (e.g. "fr", "ar", "en")
    detected_language: Optional[str] = None

    class Config:
        from_attributes = True