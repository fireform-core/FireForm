from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.api.schemas.enums import FieldSource
from app.api.schemas.incident_contract import IncidentContract


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class ExtractionHints(BaseModel):
    """Optional hints to improve extraction accuracy.

    Extra keys are allowed; the contract marks this object
    additionalProperties: true.
    """

    model_config = ConfigDict(extra="allow")

    incident_type: str | None = None
    state: str | None = None
    agency_type: str | None = None


class ExtractionDefaults(BaseModel):
    """Deployment context the extractor falls back on when the narrative is
    silent: timezone for relative dates, country, and currency for Money."""

    country: str | None = None
    timezone: str | None = None
    currency: str | None = None


class ExtractionRequest(BaseModel):
    model_override: str | None = None
    extraction_hints: ExtractionHints | None = None
    defaults: ExtractionDefaults | None = None


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------

class ExtractionJobResponse(BaseModel):
    """202 body for POST /extract/{input_id}. Carries the ids the client needs
    to poll the extraction plus the underlying async job."""

    extract_id: UUID
    input_id: UUID
    job_id: str
    job_type: str = "extraction"
    status: str
    queued_at: datetime | None = None
    estimated_seconds: int | None = None
    poll_url: str


class Correction(BaseModel):
    """One manual correction applied to the contract via PATCH."""

    field_path: str | None = None
    original_value: Any = None
    corrected_value: Any = None
    corrected_at: datetime | None = None
    corrected_by: str | None = None


class ExtractionCompleted(BaseModel):
    """A completed extraction. The contract document is embedded here, read
    from the linked incident row; the extraction itself keeps only job
    metadata and the corrections audit trail."""

    extract_id: UUID
    input_id: UUID
    incident_id: UUID
    status: Literal["completed"]
    incident_contract: IncidentContract
    completed_at: datetime | None = None
    model_used: str | None = None
    processing_time_seconds: float | None = None
    corrections: list[Correction] | None = None


class ExtractionProcessing(BaseModel):
    extract_id: UUID
    input_id: UUID
    status: Literal["processing", "failed"]
    started_at: datetime | None = None
    retry_after_seconds: int | None = None
    error_type: str | None = None
    error_detail: str | None = None
    partial_result: IncidentContract | None = None


# ---------------------------------------------------------------------------
# Validation and readiness
# ---------------------------------------------------------------------------

class FieldGap(BaseModel):
    """One template field with no value yet, with enough context for the UI to
    explain it and offer the right fix."""

    field_name: str
    source: FieldSource
    incident_mapping: str | None = None
    description: str | None = None


class ValidationRequest(BaseModel):
    """Which registered template to check the extraction against."""

    template_id: UUID


class ValidationResult(BaseModel):
    valid: bool
    template_id: UUID
    extract_id: UUID
    # form_type is an open string, not a closed enum: users register their own
    # templates and each carries its own label.
    form_type: str | None = None
    missing_required: list[FieldGap] | None = None
    missing_recommended: list[FieldGap] | None = None
    warnings: list[str] | None = None
    field_coverage_percent: float | None = None


class TemplateReadiness(BaseModel):
    template_id: UUID
    form_type: str
    display_name: str
    ready: bool
    missing_required: list[FieldGap] | None = None
    missing_recommended: list[FieldGap] | None = None
    field_coverage_percent: float | None = None


class ReadinessMatrix(BaseModel):
    """Per-template fill readiness for one extraction, computed by comparing
    the contract against every registered template's field list."""

    extract_id: UUID
    templates: list[TemplateReadiness]
    computed_at: datetime | None = None
