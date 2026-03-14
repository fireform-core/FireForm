from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class FormFill(BaseModel):
    template_id: int
    input_text: str

    class Config:
        from_attributes = True


class FormFillResponse(BaseModel):
    id: int
    template_id: int
    input_text: str
    output_pdf_path: str
    created_at: datetime

    class Config:
        from_attributes = True


# ── Batch schemas — closes #156 ───────────────────────────────

class BatchFormFill(BaseModel):
    """
    Request body for POST /forms/fill/batch.
    One transcript + multiple template IDs → fills all PDFs in one request.
    """
    input_text: str
    template_ids: list[int]

    class Config:
        from_attributes = True


class BatchResultItem(BaseModel):
    """
    Per-template result in a batch fill response.
    """
    template_id: int
    template_name: str
    success: bool
    submission_id: Optional[int] = None
    download_url: Optional[str] = None
    error: Optional[str] = None

    class Config:
        from_attributes = True


class BatchFormFillResponse(BaseModel):
    """
    Response body for POST /forms/fill/batch.
    Partial failures preserved — one failure never aborts the batch.
    """
    total: int
    succeeded: int
    failed: int
    results: list[BatchResultItem]

    class Config:
        from_attributes = True