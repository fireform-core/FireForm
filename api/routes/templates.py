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
from src.controller import Controller

router = APIRouter(prefix="/templates", tags=["templates"])
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEMPLATE_DIR = "src/inputs"
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB


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


@router.post("/create", response_model=TemplateResponse)
def create(template: TemplateCreate, db: Session = Depends(get_db)):
    controller = Controller()
    template_path = controller.create_template(template.pdf_path)
    tpl = Template(**template.model_dump(exclude={"pdf_path"}), pdf_path=template_path)
    return create_template(db, tpl)
