from pydantic import BaseModel
from typing import Optional


class FormFill(BaseModel):
    template_id: int
    input_text: str
    gps_latitude: Optional[float] = None
    gps_longitude: Optional[float] = None
    device_id: Optional[str] = None
    officer_name: Optional[str] = None


class FormFillResponse(BaseModel):
    id: int
    template_id: int
    input_text: str
    output_pdf_path: str
    gps_latitude: Optional[float] = None
    gps_longitude: Optional[float] = None
    device_id: Optional[str] = None
    officer_name: Optional[str] = None

    class Config:
        from_attributes = True