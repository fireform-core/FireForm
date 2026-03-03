from pydantic import BaseModel, ConfigDict, field_validator
from datetime import datetime


class BatchFill(BaseModel):
    """Request body for POST /forms/fill/batch."""
    input_text: str
    template_ids: list[int]

    @field_validator("template_ids")
    @classmethod
    def must_have_at_least_one(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("template_ids must contain at least one template ID")
        if len(v) > 20:
            raise ValueError("Batch size is limited to 20 templates per request")
        if len(v) != len(set(v)):
            raise ValueError("template_ids must not contain duplicates")
        return v


class TemplateResult(BaseModel):
    """Per-template result within a BatchFillResponse."""
    template_id: int
    status: str                  # complete | failed
    submission_id: int | None    # FormSubmission.id if successful
    output_pdf_path: str | None  # path to filled PDF if successful
    error: str | None            # error message if failed


class EvidenceField(BaseModel):
    """Evidence attribution for a single canonical incident field."""
    value: str | list | None
    evidence: str | None         # verbatim transcript quote
    confidence: str              # high | medium | low


class BatchFillResponse(BaseModel):
    """Response from POST /forms/fill/batch."""
    model_config = ConfigDict(from_attributes=True)

    batch_id: str
    status: str                              # complete | partial | failed
    input_text: str
    template_ids: list[int]
    results: list[TemplateResult]
    # Evidence report: canonical category -> {value, evidence, confidence}
    # Only includes categories that were successfully extracted
    evidence_report: dict[str, EvidenceField] | None
    total_requested: int
    total_succeeded: int
    total_failed: int
    created_at: datetime


class BatchStatusResponse(BaseModel):
    """Response from GET /forms/batches/{batch_id} — lightweight status check."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    template_ids: list
    submission_ids: list | None
    output_paths: dict | None
    errors: dict | None
    created_at: datetime


class AuditResponse(BaseModel):
    """
    Response from GET /forms/batches/{batch_id}/audit.

    Returns the full canonical extraction with per-field evidence attribution.
    This endpoint is specifically designed for legal compliance and chain-of-custody
    verification in emergency services contexts. Each extracted value is paired
    with the exact verbatim transcript quote that supports it, allowing supervisors
    and legal teams to verify that every value in every filed form is traceable
    back to a specific statement in the original incident transcript.
    """
    model_config = ConfigDict(from_attributes=True)

    batch_id: str
    input_text: str
    canonical_extraction: dict | None
    evidence_report: dict | None
    created_at: datetime
