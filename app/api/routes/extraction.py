from uuid import UUID

from fastapi import APIRouter, Body, Depends
from sqlmodel import Session

from app.api.deps import get_db
from app.api.schemas.enums import ExtractionStatus, InputStatus
from app.api.schemas.extraction import (
    ExtractionCompleted,
    ExtractionJobResponse,
    ExtractionProcessing,
    ExtractionRequest,
    ReadinessMatrix,
    ValidationRequest,
    ValidationResult,
)
from app.api.schemas.incident_contract import IncidentContract
from app.core.config import (
    ESTIMATED_EXTRACTION_SECONDS,
    EXTRACTION_ALLOW_RERUN,
    EXTRACTION_POLL_INTERVAL_SECONDS,
)
from app.core.errors.base import AppError
from app.db.repositories import (
    get_extraction,
    get_extraction_by_input,
    get_incident_by_extract,
    get_input,
    list_form_templates,
)
from app.models import Extraction, Incident
from app.services.extraction.service import ExtractionService
from app.services.extraction_readiness import readiness_matrix, validate_template
from app.services.extraction_review import ExtractionReviewService, load_for_review
from app.services.form_templates import require_template
from app.services import llm

router = APIRouter(prefix="/extract", tags=["extraction"])

MERGE_PATCH_MEDIA_TYPE = "application/merge-patch+json"


def _completed_response(extraction: Extraction, incident: Incident | None) -> ExtractionCompleted:
    """The completed shape, with the contract read from the incident row."""
    contract = IncidentContract.model_validate(
        (incident.incident_contract if incident else None) or {}
    )
    return ExtractionCompleted(
        extract_id=extraction.extract_id,
        input_id=extraction.input_id,
        incident_id=incident.incident_id if incident else None,
        status="completed",
        incident_contract=contract,
        completed_at=extraction.completed_at,
        model_used=extraction.model_used,
        processing_time_seconds=extraction.processing_time_seconds,
        corrections=extraction.corrections,
    )


def _load_extraction(db: Session, extract_id: UUID) -> Extraction:
    extraction = get_extraction(db, extract_id)
    if extraction is None:
        raise AppError(
            f"Extraction with ID {extract_id} not found",
            status_code=404,
            error_code="EXTRACT_NOT_FOUND",
        )
    return extraction


@router.post("/{input_id}", response_model=ExtractionJobResponse, status_code=202)
def create_extraction(
    input_id: UUID,
    body: ExtractionRequest | None = None,
    db: Session = Depends(get_db),
):
    record = get_input(db, input_id)
    if record is None:
        raise AppError(
            f"Input with ID {input_id} not found",
            status_code=404,
            error_code="INPUT_NOT_FOUND",
        )

    if record.status != InputStatus.ready:
        raise AppError(
            f"Input is in '{record.status}' state. Wait until status is 'ready'.",
            status_code=409,
            error_code="INPUT_NOT_READY",
            detail={"current_status": record.status},
        )

    existing = get_extraction_by_input(db, input_id)
    if existing is not None and not EXTRACTION_ALLOW_RERUN:
        raise AppError(
            "An extraction already exists for this input",
            status_code=409,
            error_code="EXTRACTION_EXISTS",
            detail={"existing_extract_id": str(existing.extract_id)},
        )

    provider = llm.health()
    if provider.status == "unhealthy":
        raise AppError(
            f"The {provider.label} LLM service is not available",
            status_code=503,
            error_code="LLM_UNAVAILABLE",
            detail={"provider": provider.provider, "reason": provider.detail},
        )

    svc = ExtractionService()
    extraction, job = svc.start_extraction(
        db,
        input_id,
        model_override=body.model_override if body else None,
        defaults=body.defaults if body else None,
        hints=body.extraction_hints if body else None,
    )

    return ExtractionJobResponse(
        extract_id=extraction.extract_id,
        input_id=input_id,
        job_id=job.job_id,
        status=extraction.status,
        queued_at=extraction.created_at,
        estimated_seconds=ESTIMATED_EXTRACTION_SECONDS,
        poll_url=f"/api/v1/extract/{extraction.extract_id}",
    )


@router.get("/{extract_id}", response_model=ExtractionCompleted | ExtractionProcessing)
def get_extraction_result(extract_id: UUID, db: Session = Depends(get_db)):
    extraction = _load_extraction(db, extract_id)

    if extraction.status == ExtractionStatus.completed:
        return _completed_response(extraction, get_incident_by_extract(db, extract_id))

    retry_after = (
        EXTRACTION_POLL_INTERVAL_SECONDS
        if extraction.status == ExtractionStatus.processing
        else None
    )
    partial = (
        IncidentContract.model_validate(extraction.partial_result)
        if extraction.partial_result
        else None
    )
    return ExtractionProcessing(
        extract_id=extraction.extract_id,
        input_id=extraction.input_id,
        status=extraction.status,
        started_at=extraction.started_at,
        retry_after_seconds=retry_after,
        error_type=extraction.error_type,
        error_detail=extraction.error_detail,
        partial_result=partial,
    )


@router.patch("/{extract_id}", response_model=ExtractionCompleted)
def update_extraction(
    extract_id: UUID,
    patch: dict = Body(
        ...,
        media_type=MERGE_PATCH_MEDIA_TYPE,
        description="JSON Merge Patch (RFC 7396) shaped like the incident contract. "
        "Only send the fields that changed; a null deletes a field.",
    ),
    db: Session = Depends(get_db),
):
    extraction = _load_extraction(db, extract_id)
    incident = load_for_review(extraction, get_incident_by_extract(db, extract_id))

    extraction, incident = ExtractionReviewService().apply_patch(
        db, extraction, incident, patch
    )
    return _completed_response(extraction, incident)


@router.get("/{extract_id}/readiness", response_model=ReadinessMatrix)
def get_readiness(extract_id: UUID, db: Session = Depends(get_db)):
    extraction = _load_extraction(db, extract_id)
    incident = load_for_review(extraction, get_incident_by_extract(db, extract_id))

    return readiness_matrix(extraction, incident, list_form_templates(db))


@router.post("/{extract_id}/validate", response_model=ValidationResult)
def validate_extraction(
    extract_id: UUID,
    body: ValidationRequest,
    db: Session = Depends(get_db),
):
    extraction = _load_extraction(db, extract_id)
    incident = load_for_review(extraction, get_incident_by_extract(db, extract_id))

    return validate_template(extraction, incident, require_template(db, body.template_id))
