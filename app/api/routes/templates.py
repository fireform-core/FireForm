from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session

from app.api.deps import get_db, verify_api_key
from app.api.schemas.templates import (
    MakeFillableRequest,
    MakeFillableResponse,
    TemplateCreate,
    TemplateResponse,
    TemplateUploadResponse,
)
from app.core.config import DEFAULT_TEMPLATE_DIR
from app.db.repositories import get_template
from app.services.template import TemplateService

router = APIRouter(prefix="/templates", tags=["templates"])


@router.post("/upload", response_model=TemplateUploadResponse)
async def upload_template_pdf(
    file: UploadFile = File(...),
    directory: str = Form(DEFAULT_TEMPLATE_DIR),
):
    filename = Path(file.filename or "").name
    if not filename:
        raise HTTPException(status_code=400, detail="A PDF filename is required.")

    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    content = await file.read()
    return TemplateService().save_uploaded_pdf(directory, filename, content)


@router.get("", response_model=list[TemplateResponse])
def get_templates(db: Session = Depends(get_db)):
    return TemplateService().list_templates(db)


@router.get("/preview")
def preview_template_pdf(path: str = Query(..., description="Project-relative PDF path")):
    resolved_path = TemplateService().resolve_pdf_path(path)

    if not resolved_path.exists() or not resolved_path.is_file():
        raise HTTPException(status_code=404, detail="PDF file not found.")

    if resolved_path.suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Only PDF files can be previewed.")

    return FileResponse(
        resolved_path,
        media_type="application/pdf",
        filename=resolved_path.name,
        content_disposition_type="inline",
    )


@router.post("/create", response_model=TemplateResponse)
def create(template: TemplateCreate, db: Session = Depends(get_db)):
    return TemplateService().create_template(db, template)


@router.post("/make-fillable", response_model=MakeFillableResponse)
def make_fillable(req: MakeFillableRequest):
    svc = TemplateService()
    resolved = svc.resolve_pdf_path(req.pdf_path)
    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="PDF file not found.")

    return svc.make_fillable(str(resolved))


@router.delete("/{template_id}", dependencies=[Depends(verify_api_key)])
def delete_template_endpoint(template_id: int, db: Session = Depends(get_db)):
    template = get_template(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    TemplateService().delete_template(db, template)
    return {"status": "success", "message": "Template and all associated data deleted"}
