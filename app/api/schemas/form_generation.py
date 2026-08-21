"""Contract Layer 3 form generation schemas (contracts/schemas/form-record.yaml).

Separate from app/api/schemas/forms.py, which holds the legacy prototype
fill-pipeline shapes (int template_id, no incident/batch concept) still served
by the old routes in app/api/routes/forms.py. This file is the v1 contract
shape only — mirrors the extraction.py / templates.py split, one file per
contract domain.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.api.schemas.enums import FormStatus, OutputFormat


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class GenerateFormsOptions(BaseModel):
    output_format: OutputFormat | None = None
    force_partial: bool = False


class GenerateFormsRequest(BaseModel):
    """POST /forms/generate body.

    template_ids is required in this build: omitting it (generate every
    template the readiness matrix reports as ready) is #554, not built here.
    """

    incident_id: UUID
    template_ids: list[UUID] = Field(min_length=1)
    options: GenerateFormsOptions | None = None


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------

class QueuedForm(BaseModel):
    form_id: UUID
    template_id: UUID
    form_type: str


class SkippedForm(BaseModel):
    template_id: UUID
    form_type: str
    reason: str


class BatchGenerateResponse(BaseModel):
    """202 body for POST /forms/generate."""

    batch_id: UUID
    status: Literal["processing"] = "processing"
    incident_id: UUID
    forms_queued: list[QueuedForm] = Field(default_factory=list)
    forms_skipped: list[SkippedForm] = Field(default_factory=list)
    estimated_seconds: int | None = None
    poll_url: str


class FieldMappingSummary(BaseModel):
    total_form_fields: int
    fields_filled: int
    fields_blank: int
    coverage_percent: float


class FormRecord(BaseModel):
    """GET /forms/{form_id} response."""

    form_id: UUID
    template_id: UUID
    # form_type is an open string on the wire: registries can add form types
    # the closed FormType enum does not know about yet (see FormTemplate.form_type).
    form_type: str
    status: FormStatus
    incident_id: UUID
    batch_id: UUID | None = None
    created_at: datetime
    completed_at: datetime | None = None
    pdf_ready: bool
    json_ready: bool
    field_mapping_summary: FieldMappingSummary | None = None


class FormMappedJson(BaseModel):
    """GET /forms/{form_id}/json response."""

    form_type: str
    form_id: UUID
    template_id: UUID
    incident_id: UUID
    agency_fields: dict = Field(default_factory=dict)


class BatchFormEntry(BaseModel):
    form_id: UUID
    template_id: UUID
    form_type: str
    status: FormStatus


class BatchStatus(BaseModel):
    """GET /forms/batch/{batch_id} response, derived on the fly from the
    batch's Form rows — there is no Batch table."""

    batch_id: UUID
    status: Literal["processing", "completed", "failed"]
    total: int
    completed: int
    failed: int
    forms: list[BatchFormEntry] = Field(default_factory=list)
    # Zip bundling of a batch's PDFs is #554; always null here.
    download_url: str | None = None


__all__ = [
    "GenerateFormsOptions",
    "GenerateFormsRequest",
    "QueuedForm",
    "SkippedForm",
    "BatchGenerateResponse",
    "FieldMappingSummary",
    "FormRecord",
    "FormMappedJson",
    "BatchFormEntry",
    "BatchStatus",
]
