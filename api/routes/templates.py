import re
from sqlalchemy.exc import IntegrityError
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session

from api.deps import get_db
from api.db.models import Template
from api.db.repositories import (
    create_template,
    delete_template,
    get_template,
    update_template,
    list_templates
)
from api.schemas.templates import TemplateResponse, TemplateUpdate
from src.controller import Controller

router = APIRouter(prefix="/templates", tags=["templates"])

INPUT_FILES_DIR = Path(__file__).resolve().parents[2] / "template_files"


def _safe_name_fragment(name: str) -> str:
    base = Path(name).name
    s = re.sub(r"[^\w\-.]+", "_", base.strip(), flags=re.UNICODE)
    s = s.strip("._-") or "template"
    return s[:120]


@router.post("/create", response_model=TemplateResponse)
def create(
    name: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    filename = (file.filename or "").lower()
    if not filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a .pdf")

    frag = _safe_name_fragment(name)
    uid = uuid.uuid4().hex
    INPUT_FILES_DIR.mkdir(parents=True, exist_ok=True)
    dest = INPUT_FILES_DIR / f"{frag}_{uid}.pdf"

    raw = file.file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")
    dest.write_bytes(raw)

    controller = Controller()
    try:
        template_path = controller.create_template(str(dest))
    except Exception as e:
        dest.unlink(missing_ok=True)
        print(e)
        raise HTTPException(
            status_code=500, detail=f"Failed to prepare PDF template: {e}"
        ) from e

    fields = controller.extract_template_fields(template_path)
    tpl = Template(name=name.strip(), fields=fields, pdf_path=template_path)

    try:
        return create_template(db, tpl)
    except IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="A template with the same name already  exists"
        )

@router.get("/", response_model=list[Template])
def list(db: Session = Depends(get_db)):
    return list_templates(db)


@router.get("/{template_id}/pdf")
def get_template_pdf(template_id: int, db: Session = Depends(get_db)):
    """Serve the stored PDF for preview in the schema wizard."""
    tpl = get_template(db, template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    root = INPUT_FILES_DIR.resolve()
    path = Path(tpl.pdf_path).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid template file location")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="PDF file missing on disk")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"{tpl.name}.pdf",
    )


@router.get("/{template_id}", response_model=TemplateResponse)
def get_one(template_id: int, db: Session = Depends(get_db)):
    tpl = get_template(db, template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    return tpl


@router.put("/{template_id}", response_model=TemplateResponse)
def update_one(
    template_id: int,
    data: TemplateUpdate,
    db: Session = Depends(get_db),
):
    updates = data.model_dump(exclude_none=True)
    if not updates:
        tpl = get_template(db, template_id)
        if not tpl:
            raise HTTPException(status_code=404, detail="Template not found")
        return tpl
    tpl = update_template(db, template_id, updates)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    return tpl


@router.delete("/{template_id}")
def delete_one(template_id: int, db: Session = Depends(get_db)):
    if not delete_template(db, template_id):
        raise HTTPException(status_code=404, detail="Template not found")
    return {"detail": "Template deleted"}
