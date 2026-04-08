from pydantic import BaseModel
from typing import Optional

class FormFill(BaseModel):
    template_id: int
    input_text: str
    model: Optional[str] = None  # e.g. "mistral", "llama3", "phi3" — defaults to LLM_MODEL env var


class FormFillResponse(BaseModel):
    id: int
    template_id: int
    input_text: str
    output_pdf_path: str

    class Config:
        from_attributes = True