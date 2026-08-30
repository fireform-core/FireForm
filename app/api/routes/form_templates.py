"""Contract Layer 6 template registry endpoints (contracts/path/templates.yaml).

Serves the form-template registry at /api/v1/templates, backed by the
UUID-keyed `FormTemplate` model, plus the PDF-authoring flow that feeds it:
upload a blank PDF, poll the detection draft, register the edited fields.
Handlers are thin, business logic lives in app/services/form_templates.py. The
legacy prototype template routes (upload / create / make-fillable / preview /
delete) were removed in the contract migration; the legacy int-PK `Template`
model survives only as the lookup target of the fill pipeline (forms.py /
jobs.py / tasks/fill.py).
"""

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session

from app.api.deps import get_db
from app.api.schemas.templates import (
    CreateTemplateRequest,
    TemplateDetail,
    TemplateDraft,
    TemplateDraftAccepted,
    TemplateFieldsResponse,
    TemplateSummary,
)
from app.core.config import MAX_TEMPLATE_PDF_BYTES
from app.core.errors.base import AppError
from app.services import form_templates as service

router = APIRouter(prefix="/templates", tags=["templates"])

_PDF_MAGIC = b"%PDF-"


def _reject_if_too_large(size: int | None) -> None:
    """Guard the 50MB cap. Checked once on the declared size before the body is
    read into memory, and again on what actually arrived."""
    if size is None or size <= MAX_TEMPLATE_PDF_BYTES:
        return
    raise AppError(
        "PDF exceeds maximum size of 50MB",
        status_code=413,
        error_code="FILE_TOO_LARGE",
        detail={
            "max_size_bytes": MAX_TEMPLATE_PDF_BYTES,
            "received_size_bytes": size,
        },
    )


@router.get("", response_model=list[TemplateSummary])
def list_templates(db: Session = Depends(get_db)):
    return service.list_templates(db)


@router.post("", response_model=TemplateDetail, status_code=201)
def create_template(body: CreateTemplateRequest, db: Session = Depends(get_db)):
    return service.create_template(db, body)


# The two /pdf routes are declared before /{template_id} on purpose. FastAPI
# matches in declaration order, so the literal path has to come first or "pdf"
# gets read as a template id.
@router.post("/pdf", response_model=TemplateDraftAccepted, status_code=202)
def upload_template_pdf(
    pdf_file: UploadFile = File(...),
    detect_fields: bool = Form(default=True),
    db: Session = Depends(get_db),
):
    filename = pdf_file.filename or ""

    _reject_if_too_large(pdf_file.size)

    content = pdf_file.file.read()
    if not content:
        raise AppError(
            "No PDF file was uploaded",
            status_code=400,
            error_code="MISSING_FILE",
        )
    _reject_if_too_large(len(content))
    # Trust the bytes, not the extension or the declared content type.
    if not content.startswith(_PDF_MAGIC):
        raise AppError(
            "Uploaded file is not a PDF",
            status_code=415,
            error_code="UNSUPPORTED_FORMAT",
            detail={"accepted_formats": ["pdf"]},
        )

    upload, job = service.store_upload(db, content, filename or None, detect_fields)
    return service.draft_response(upload, job)


@router.get("/pdf/{upload_id}", response_model=TemplateDraft)
def get_template_draft(upload_id: UUID, db: Session = Depends(get_db)):
    return service.get_draft(db, upload_id)


@router.get("/{template_id}", response_model=TemplateDetail)
def get_template(template_id: UUID, db: Session = Depends(get_db)):
    return service.get_template(db, template_id)


@router.put("/{template_id}", response_model=TemplateDetail)
def replace_template(
    template_id: UUID, body: CreateTemplateRequest, db: Session = Depends(get_db)
):
    return service.replace_template(db, template_id, body)


@router.get("/{template_id}/fields", response_model=TemplateFieldsResponse)
def get_template_fields(
    template_id: UUID,
    required_only: bool = Query(False, description="Return only required fields"),
    db: Session = Depends(get_db),
):
    return service.get_template_fields(db, template_id, required_only)


@router.get("/{template_id}/pdf", response_class=FileResponse)
def download_template_pdf(template_id: UUID, db: Session = Depends(get_db)):
    path: Path = service.resolve_template_pdf(db, template_id)
    return FileResponse(path, media_type="application/pdf", filename=path.name)
