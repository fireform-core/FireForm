"""Business logic for the contract Layer 6 template registry.

Sits between the route handlers (app/api/routes/form_templates.py) and the
repositories. No FastAPI imports here — handlers do HTTP, this does the work:
validation/conflict checks, ORM construction, and ORM -> response mapping
(including the derived `field_count` / `last_updated`).
"""

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from sqlmodel import Session

from app.api.schemas.enums import DetectionStatus, JobType
from app.api.schemas.templates import (
    CreateTemplateRequest,
    DraftField,
    PageGeometry,
    TemplateDetail,
    TemplateDraft,
    TemplateDraftAccepted,
    TemplateField,
    TemplateFieldsResponse,
    TemplateSummary,
)
from app.core.config import (
    DATA_DIR,
    TEMPLATE_DETECTION_POLL_INTERVAL_SECONDS,
    TEMPLATE_UPLOAD_DIR,
)
from app.core.errors.base import AppError
from app.db.repositories import (
    create_form_template,
    create_job,
    create_template_upload,
    get_form_template,
    get_form_template_by_form_type,
    get_template_upload,
    list_form_templates,
    update_form_template,
    update_job,
)
from app.models import FormTemplate, Job, TemplateUpload
from app.services.template_detection import read_pages
from app.tasks.detect_fields import detect_template_fields_task


# ---------------------------------------------------------------------------
# Mapping helpers (ORM -> response schema). field_count / last_updated are
# derived here rather than stored on the model.
# ---------------------------------------------------------------------------
def _field_count(template: FormTemplate) -> int:
    return len(template.fields or [])


def _to_summary(template: FormTemplate) -> TemplateSummary:
    return TemplateSummary(
        template_id=template.template_id,
        form_type=template.form_type,
        display_name=template.display_name,
        jurisdiction=template.jurisdiction,
        agency_type=template.agency_type,
        version=template.version,
        last_updated=template.updated_at.date(),
        field_count=_field_count(template),
        status=template.status,
    )


def _to_detail(template: FormTemplate) -> TemplateDetail:
    return TemplateDetail(
        template_id=template.template_id,
        form_type=template.form_type,
        display_name=template.display_name,
        jurisdiction=template.jurisdiction,
        agency_type=template.agency_type,
        fields=template.fields,
        source_standard=template.source_standard,
        pdf_template_ref=template.pdf_template_ref,
        version=template.version,
        last_updated=template.updated_at.date(),
        field_count=_field_count(template),
        status=template.status,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


def require_template(db: Session, template_id: UUID) -> FormTemplate:
    template = get_form_template(db, template_id)
    if not template:
        raise AppError(
            f"Template {template_id} not found",
            status_code=404,
            error_code="TEMPLATE_NOT_FOUND",
        )
    return template


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------
def list_templates(db: Session) -> list[TemplateSummary]:
    return [_to_summary(t) for t in list_form_templates(db)]


def create_template(db: Session, body: CreateTemplateRequest) -> TemplateDetail:
    if get_form_template_by_form_type(db, body.form_type):
        raise AppError(
            f"Template with form_type '{body.form_type}' already exists",
            status_code=409,
            error_code="TEMPLATE_EXISTS",
        )

    template = FormTemplate(
        form_type=body.form_type,
        display_name=body.display_name,
        jurisdiction=body.jurisdiction,
        agency_type=body.agency_type,
        fields=[f.model_dump(mode="json") for f in body.fields],
        source_standard=body.source_standard,
        pdf_template_ref=body.pdf_template_ref,
    )
    return _to_detail(create_form_template(db, template))


def get_template(db: Session, template_id: UUID) -> TemplateDetail:
    return _to_detail(require_template(db, template_id))


def replace_template(
    db: Session, template_id: UUID, body: CreateTemplateRequest
) -> TemplateDetail:
    template = require_template(db, template_id)

    # form_type is unique in the DB, so a rename onto a form_type another
    # template already holds has to be answered here. Without this the insert
    # fails deep in the session and the client gets a bare 500.
    clash = get_form_template_by_form_type(db, body.form_type)
    if clash and clash.template_id != template_id:
        raise AppError(
            f"Template with form_type '{body.form_type}' already exists",
            status_code=409,
            error_code="TEMPLATE_EXISTS",
        )

    # Contract defines a 409 TEMPLATE_IN_USE when submitted incidents reference
    # this template. The contract forms/incidents layers tie records to
    # extract_id + form_type, never template_id, so there is no linkage to query
    # yet. Once a form_type<->submission link exists, gate the update here.
    # TODO(contract): enforce 409 TEMPLATE_IN_USE.

    template.form_type = body.form_type
    template.display_name = body.display_name
    template.jurisdiction = body.jurisdiction
    template.agency_type = body.agency_type
    template.fields = [f.model_dump(mode="json") for f in body.fields]
    template.source_standard = body.source_standard
    template.pdf_template_ref = body.pdf_template_ref
    template.updated_at = datetime.now(timezone.utc)
    return _to_detail(update_form_template(db, template))


def resolve_template_pdf(db: Session, template_id: UUID) -> Path:
    """On-disk path of a template's source PDF.

    `pdf_template_ref` is client-supplied, so the resolved path is checked to
    still sit under the data directory before anything is served from it.
    """
    template = require_template(db, template_id)
    if not template.pdf_template_ref:
        raise AppError(
            f"Template {template_id} has no source PDF",
            status_code=404,
            error_code="TEMPLATE_PDF_NOT_FOUND",
        )

    path = (DATA_DIR / template.pdf_template_ref).resolve()
    if not path.is_relative_to(DATA_DIR) or not path.is_file():
        raise AppError(
            f"Source PDF for template {template_id} is missing",
            status_code=404,
            error_code="TEMPLATE_PDF_NOT_FOUND",
        )
    return path


# ---------------------------------------------------------------------------
# PDF upload and field detection
# ---------------------------------------------------------------------------
def _to_draft(upload: TemplateUpload) -> TemplateDraft:
    return TemplateDraft(
        upload_id=upload.upload_id,
        status=upload.status,
        pdf_template_ref=upload.pdf_template_ref,
        original_filename=upload.original_filename,
        page_count=upload.page_count,
        pages=[PageGeometry(**page) for page in upload.pages],
        detected_fields=(
            [DraftField(**field) for field in upload.detected_fields]
            if upload.detected_fields is not None
            else None
        ),
        detection_error=upload.detection_error,
        retry_after_seconds=(
            TEMPLATE_DETECTION_POLL_INTERVAL_SECONDS
            if upload.status == DetectionStatus.processing
            else None
        ),
    )


def store_upload(
    db: Session, content: bytes, filename: str | None, detect_fields: bool
) -> tuple[TemplateUpload, Job | None]:
    """Store a blank PDF, read its page geometry, and queue field detection.

    The PDF and its geometry are saved before returning, so the editor can
    render pages immediately. Only detection runs in the background, and with
    `detect_fields` off the draft is complete the moment it is created.
    """
    upload_id = uuid4()
    TEMPLATE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = TEMPLATE_UPLOAD_DIR / f"{upload_id}.pdf"
    pdf_path.write_bytes(content)

    try:
        pages = read_pages(pdf_path)
    except Exception as exc:
        pdf_path.unlink(missing_ok=True)
        raise AppError(
            "Uploaded file could not be read as a PDF",
            status_code=415,
            error_code="INVALID_PDF",
            detail={"reason": str(exc)},
        )

    upload = TemplateUpload(
        upload_id=upload_id,
        status=DetectionStatus.processing if detect_fields else DetectionStatus.completed,
        pdf_path=str(pdf_path),
        pdf_template_ref=str(pdf_path.relative_to(DATA_DIR)),
        original_filename=filename,
        page_count=len(pages),
        pages=[page.model_dump() for page in pages],
        detected_fields=None if detect_fields else [],
    )

    if not detect_fields:
        return create_template_upload(db, upload), None

    # Same order as the voice upload: create the job, dispatch, then backfill
    # the celery id. A failure anywhere after the file write takes the file
    # with it rather than leaving an upload nobody can finish.
    try:
        job = create_job(
            db,
            Job(celery_task_id="", job_type=JobType.template_field_detection, status="queued"),
        )
        upload.job_id = job.job_id
        upload = create_template_upload(db, upload)
        result = detect_template_fields_task.delay(str(upload.upload_id), job.job_id)
        job.celery_task_id = result.id
        update_job(db, job)
    except Exception:
        pdf_path.unlink(missing_ok=True)
        raise

    return upload, job


def get_draft(db: Session, upload_id: UUID) -> TemplateDraft:
    upload = get_template_upload(db, upload_id)
    if not upload:
        raise AppError(
            f"Upload {upload_id} not found",
            status_code=404,
            error_code="UPLOAD_NOT_FOUND",
        )
    return _to_draft(upload)


def draft_response(upload: TemplateUpload, job: Job | None) -> TemplateDraftAccepted:
    """The 202 body: the draft the editor can already render, plus where to poll."""
    draft = _to_draft(upload)
    return TemplateDraftAccepted(
        **draft.model_dump(),
        job_id=job.job_id if job else None,
        poll_url=f"/api/v1/templates/pdf/{upload.upload_id}",
    )


def get_template_fields(
    db: Session, template_id: UUID, required_only: bool
) -> TemplateFieldsResponse:
    template = require_template(db, template_id)

    fields = [TemplateField(**f) for f in template.fields]
    required = [f for f in fields if f.required]
    selected = required if required_only else fields

    return TemplateFieldsResponse(
        template_id=template.template_id,
        form_type=template.form_type,
        total_fields=len(fields),
        required_fields=len(required),
        optional_fields=len(fields) - len(required),
        fields=selected,
    )
