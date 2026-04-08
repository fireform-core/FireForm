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
    needs_review: Optional[dict] = None  # Fields the LLM was not confident about; must be verified by a human

    class Config:
        from_attributes = True