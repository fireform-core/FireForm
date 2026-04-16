from pydantic import BaseModel


class FieldRect(BaseModel):
    """Bounding box coordinates for a detected PDF form field."""

    x: float
    y: float
    width: float
    height: float


class DetectedField(BaseModel):
    """Metadata for a single detected interactive form field."""

    field_name: str
    field_type: str  # "Text", "Button", "Choice", or "Unknown"
    raw_type: str  # "/Tx", "/Btn", "/Ch"
    rect: FieldRect


class PageFields(BaseModel):
    """All detected fields on a single PDF page."""

    page_number: int
    fields: list[DetectedField]


class DetectFieldsResponse(BaseModel):
    """Response schema for the /wizard/detect-fields endpoint."""

    filename: str
    total_pages: int
    total_fields: int
    pages: list[PageFields]
