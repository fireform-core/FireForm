"""Contract Layer 3 form generation endpoints (contracts/path/forms.yaml).

Serves POST /forms/generate and the retrieval endpoints at /api/v1/forms,
backed by the v1 Form model. Handlers are thin; business logic lives in
app/services/form_generation.py (write path) and app/services/form_fill_worker.py
(the Celery-dispatched fill). Distinct from the legacy prototype routes in
app/api/routes/forms.py (int template_id, no incident/batch concept), which
stay mounted at the same "/forms" prefix unchanged.

/batch/{batch_id} is declared before /{form_id} for the same reason
form_templates.py declares /pdf before /{template_id}: FastAPI matches paths
in declaration order, so the literal segment has to come first or "batch"
gets read as a form_id.
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, JSONResponse
from sqlmodel import Session

from app.api.deps import get_db
from app.api.schemas.enums import FormStatus
from app.api.schemas.form_generation import (
    BatchFormEntry,
    BatchGenerateResponse,
    BatchStatus,
    FormMappedJson,
    FormRecord,
    GenerateFormsRequest,
    QueuedForm,
    SkippedForm,
)
from app.core.config import (
    DATA_DIR,
    ESTIMATED_FORM_GENERATION_SECONDS,
    FORM_GENERATION_POLL_INTERVAL_SECONDS,
)
from app.core.errors.base import AppError
from app.db.repositories import get_form, list_forms_by_batch
from app.services.form_generation import (
    FormGenerationService,
    download_filename,
    form_version,
)

router = APIRouter(prefix="/forms", tags=["forms"])


@router.post("/generate", response_model=BatchGenerateResponse, status_code=202)
def generate_forms(body: GenerateFormsRequest, db: Session = Depends(get_db)):
    result = FormGenerationService().start_generation(db, body)
    return BatchGenerateResponse(
        batch_id=result.batch_id,
        incident_id=result.incident_id,
        forms_queued=[
            QueuedForm(form_id=f.form_id, template_id=f.template_id, form_type=f.form_type)
            for f in result.queued
        ],
        forms_skipped=[
            SkippedForm(template_id=s.template_id, form_type=s.form_type, reason=s.reason)
            for s in result.skipped
        ],
        estimated_seconds=ESTIMATED_FORM_GENERATION_SECONDS,
        poll_url=f"/api/v1/forms/batch/{result.batch_id}",
    )


@router.get("/batch/{batch_id}", response_model=BatchStatus)
def get_batch_status(batch_id: UUID, db: Session = Depends(get_db)):
    forms = list_forms_by_batch(db, batch_id)
    if not forms:
        raise AppError(f"Batch {batch_id} not found", status_code=404, error_code="BATCH_NOT_FOUND")

    completed = sum(1 for f in forms if f.status == FormStatus.completed)
    failed = sum(1 for f in forms if f.status == FormStatus.failed)
    total = len(forms)
    done = completed + failed
    if done < total:
        status = "processing"
    elif failed == total:
        status = "failed"
    else:
        # Per design, a per-form failure doesn't fail the batch: the Job (and
        # this status) reads "completed" as long as every form reached a
        # terminal state and at least one succeeded — the forms list below
        # still shows exactly which ones failed.
        status = "completed"

    return BatchStatus(
        batch_id=batch_id,
        status=status,
        total=total,
        completed=completed,
        failed=failed,
        forms=[
            BatchFormEntry(
                form_id=f.form_id,
                template_id=f.template_id,
                form_type=f.form_type,
                status=f.status,
            )
            for f in forms
        ],
        download_url=None,
    )


@router.get("/{form_id}", response_model=FormRecord)
def get_form_record(form_id: UUID, db: Session = Depends(get_db)):
    form = get_form(db, form_id)
    if not form:
        raise AppError(f"Form {form_id} not found", status_code=404, error_code="FORM_NOT_FOUND")

    return FormRecord(
        form_id=form.form_id,
        template_id=form.template_id,
        form_type=form.form_type,
        status=form.status,
        incident_id=form.incident_id,
        batch_id=form.batch_id,
        created_at=form.created_at,
        completed_at=form.completed_at,
        pdf_ready=form.pdf_ready,
        json_ready=form.json_ready,
        field_mapping_summary=form.field_mapping_summary,
    )


@router.get("/{form_id}/pdf", response_class=FileResponse)
def download_form_pdf(form_id: UUID, db: Session = Depends(get_db)):
    form = get_form(db, form_id)
    if not form:
        raise AppError(f"Form {form_id} not found", status_code=404, error_code="FORM_NOT_FOUND")

    if form.status == FormStatus.failed:
        raise AppError(
            f"Form {form_id} failed to generate",
            status_code=500,
            error_code="PDF_GENERATION_FAILED",
            detail={"reason": "Form generation failed"},
        )

    if not form.pdf_ready or not form.pdf_path:
        return JSONResponse(
            status_code=202,
            content={
                "message": "Form generation is still in progress",
                "status": form.status,
                "retry_after_seconds": FORM_GENERATION_POLL_INTERVAL_SECONDS,
            },
        )

    path = (DATA_DIR / form.pdf_path).resolve()
    if not path.is_relative_to(DATA_DIR) or not path.is_file():
        raise AppError(f"Form {form_id} not found", status_code=404, error_code="FORM_NOT_FOUND")

    return FileResponse(
        path, media_type="application/pdf", filename=download_filename(db, form)
    )


@router.get("/{form_id}/json", response_model=FormMappedJson)
def get_form_json(form_id: UUID, db: Session = Depends(get_db)):
    form = get_form(db, form_id)
    if not form:
        raise AppError(f"Form {form_id} not found", status_code=404, error_code="FORM_NOT_FOUND")

    # Same three answers as /pdf, so a client polling both after one generate
    # call reads them the same way: 500 once the fill failed, 202 while it is
    # still running, the payload once it is there.
    if form.status == FormStatus.failed:
        raise AppError(
            f"Form {form_id} failed to generate",
            status_code=500,
            error_code="FORM_GENERATION_FAILED",
            detail={"reason": "Form generation failed"},
        )

    if not form.json_ready or form.json_data is None:
        return JSONResponse(
            status_code=202,
            content={
                "message": "Form generation is still in progress",
                "status": form.status,
                "retry_after_seconds": FORM_GENERATION_POLL_INTERVAL_SECONDS,
            },
        )

    return FormMappedJson(
        form_type=form.form_type,
        form_version=form_version(db, form),
        form_id=form.form_id,
        template_id=form.template_id,
        incident_id=form.incident_id,
        agency_fields=form.json_data,
    )
