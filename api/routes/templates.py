import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session
from api.deps import get_db
from api.schemas.templates import (
    TemplateCreate,
    TemplateResponse,
    TemplateUploadResponse,
    MakeFillableRequest,
    MakeFillableResponse,
)
from api.db.repositories import create_template, list_templates
from api.db.models import Template
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
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        target_path = target_dir / f"{target_path.stem}_{timestamp}{target_path.suffix}"

    content = await file.read()
    with target_path.open("wb") as output_file:
        output_file.write(content)

    relative_path = target_path.relative_to(PROJECT_ROOT).as_posix()
    extracted = _extract_pdf_fields(relative_path)
    return TemplateUploadResponse(
        filename=target_path.name,
        pdf_path=relative_path,
        field_count=None if extracted is None else len(extracted),
        fields=extracted or [],
    )


# PDF field-type codes -> the type values the frontend field builder uses.
_FIELD_TYPE_BY_FT = {"/Tx": "string", "/Btn": "checkbox", "/Ch": "list", "/Sig": "signature"}


def _pdf_text(value) -> str:
    """Decode a pdfrw string (field name / tooltip) to plain text."""
    if value is None:
        return ""
    if hasattr(value, "to_unicode"):
        return value.to_unicode().strip()
    return str(value).strip()


def _humanize(name: str) -> str:
    """Turn a raw field name into a readable description (JobTitle -> Job Title)."""
    text = re.sub(r"_+", " ", name)
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_pdf_fields(pdf_path: str) -> list[dict] | None:
    """Fillable widgets in the same order Filler.fill_form writes them
    (top-to-bottom, left-to-right per page), so seeded rows line up with the
    fill order. Returns None if the PDF can't be read."""
    try:
        from pdfrw import PdfReader
        candidate = Path(pdf_path)
        if not candidate.is_absolute():
            candidate = (PROJECT_ROOT / candidate).resolve()
        pdf = PdfReader(str(candidate))
        fields: list[dict] = []
        for page in pdf.pages:
            widgets = [a for a in (page.Annots or []) if a.Subtype == "/Widget" and a.T]
            widgets.sort(key=lambda a: (-float(a.Rect[1]), float(a.Rect[0])))
            for annot in widgets:
                name = _pdf_text(annot.T)
                fields.append({
                    "name": name,
                    "description": _pdf_text(annot.TU) or _humanize(name),
                    "type": _FIELD_TYPE_BY_FT.get(str(annot.FT), "string"),
                })
        return fields
    except Exception:
        return None


def _count_pdf_widgets(pdf_path: str) -> int | None:
    """Number of fillable widgets in a PDF, or None if unreadable."""
    fields = _extract_pdf_fields(pdf_path)
    return None if fields is None else len(fields)


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

    return FileResponse(
        resolved_path,
        media_type="application/pdf",
        filename=resolved_path.name,
        content_disposition_type="inline",
    )


@router.post("/create", response_model=TemplateResponse)
def create(template: TemplateCreate, db: Session = Depends(get_db)):
    tpl = Template(**template.model_dump())
    created = create_template(db, tpl)
    return TemplateResponse(
        id=created.id,
        name=created.name,
        pdf_path=created.pdf_path,
        fields=created.fields,
        field_count=_count_pdf_widgets(created.pdf_path),
    )


@router.post("/make-fillable", response_model=MakeFillableResponse)
def make_fillable(req: MakeFillableRequest):
    # Validate the path stays inside the project root.
    resolved = _resolve_project_file(req.pdf_path)
    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="PDF file not found.")

    controller = Controller()
    new_absolute = controller.prepare_fillable(str(resolved))
    new_path = Path(new_absolute)
    if not new_path.is_absolute():
        new_path = (PROJECT_ROOT / new_path).resolve()
    relative_path = new_path.relative_to(PROJECT_ROOT).as_posix()

    return MakeFillableResponse(
        pdf_path=relative_path,
        field_count=_count_pdf_widgets(relative_path),
    )
