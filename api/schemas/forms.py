from pydantic import BaseModel
from typing import Optional

class FormFill(BaseModel):
    template_id: int
    input_text: str
    use_batch_processing: Optional[bool] = True


class FormFillResponse(BaseModel):
    id: int
    template_id: int
    input_text: str
    output_pdf_path: str

    class Config:
        from_attributes = True