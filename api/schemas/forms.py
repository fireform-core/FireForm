from pydantic import BaseModel, ConfigDict

class FormFill(BaseModel):
    template_id: int
    input_text: str


class FormFillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    template_id: int
    input_text: str
    output_pdf_path: str