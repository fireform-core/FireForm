from pydantic import BaseModel
from typing import Optional

class FormFill(BaseModel):
    template_id: int
    input_text: str
    profile_name: Optional[str] = None


class FormFillResponse(BaseModel):
    id: int
    template_id: int
    input_text: str
    output_pdf_path: str

    class Config:
        from_attributes = True