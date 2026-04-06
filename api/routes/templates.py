import re
from sqlalchemy.exc import IntegrityError
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session

from api.deps import get_db
from api.schemas.templates import (
    TemplateCreate,
    TemplateResponse,
    TemplateUploadResponse,
)
from api.db.repositories import create_template, list_templates
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
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEMPLATE_DIR = "src/inputs"


def _resolve_target_directory(directory: str) -> Path:
    dir_value = (directory or DEFAULT_TEMPLATE_DIR).strip()
    if not dir_value:
        raise HTTPException(status_code=400, detail="Directory is required.")

    candidate = Path(dir_value)
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    else:
        candidate = candidate.resolve()

    if candidate != PROJECT_ROOT and PROJECT_ROOT not in candidate.parents:
        raise HTTPException(status_code=400, detail="Directory must be inside the project.")

    return candidate


def _resolve_project_file(file_path: str) -> Path:
    raw_path = (file_path or "").strip()
    if not raw_path:
        raise HTTPException(status_code=400, detail="Path is required.")

    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    else:
        candidate = candidate.resolve()

    if candidate != PROJECT_ROOT and PROJECT_ROOT not in candidate.parents:
        raise HTTPException(status_code=400, detail="Path must be inside the project.")

    return candidate


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

    target_dir = _resolve_target_directory(directory)
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / filename
    if target_path.exists():
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        target_path = target_dir / f"{target_path.stem}_{timestamp}{target_path.suffix}"

    content = await file.read()
    with target_path.open("wb") as output_file:
        output_file.write(content)

    return TemplateUploadResponse(
        filename=target_path.name,
        pdf_path=target_path.relative_to(PROJECT_ROOT).as_posix(),
    )


@router.get("", response_model=list[TemplateResponse])
def get_templates(db: Session = Depends(get_db)):
    return list_templates(db)


@router.get("/preview")
def preview_template_pdf(path: str = Query(..., description="Project-relative PDF path")):
    resolved_path = _resolve_project_file(path)

    if not resolved_path.exists() or not resolved_path.is_file():
        raise HTTPException(status_code=404, detail="PDF file not found.")

    if resolved_path.suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Only PDF files can be previewed.")

    return FileResponse(resolved_path, media_type="application/pdf", filename=resolved_path.name)


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
