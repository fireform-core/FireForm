from pydantic import BaseModel

class FormFill(BaseModel):
    template_id: int
    input_text: str


class FormFillResponse(BaseModel):
    id: int
    template_id: int
    input_text: str
    output_pdf_path: str

    class Config:
        from_attributes = True