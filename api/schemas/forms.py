from pydantic import BaseModel, ConfigDict
from datetime import datetime


class FormFill(BaseModel):
    template_id: int
    input_text: str


class FormFillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    template_id: int
    input_text: str
    output_pdf_path: str


# ── Async / streaming schemas ──────────────────────────────────────────────────

class AsyncFillSubmitted(BaseModel):
    """Returned immediately (HTTP 202) when a background fill job is accepted."""
    job_id: str
    status: str


class JobStatusResponse(BaseModel):
    """Returned by GET /forms/jobs/{job_id} — reflects current state of a FillJob."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str           # pending | running | complete | failed
    template_id: int
    input_text: str
    output_pdf_path: str | None
    partial_results: dict | None    # field -> extracted value (updated incrementally)
    field_confidence: dict | None   # field -> "high" | "medium" | "low"
    error_message: str | None
    created_at: datetime
