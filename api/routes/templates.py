import os
import shutil
import uuid
from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlmodel import Session
from api.deps import get_db
from api.schemas.templates import TemplateResponse
from api.db.repositories import create_template, get_all_templates
from api.db.models import Template
from api.errors.base import AppError

router = APIRouter(prefix="/templates", tags=["templates"])

# Save directly into src/inputs/ — stable location, won't get wiped
TEMPLATES_DIR = os.path.join("src", "inputs")
os.makedirs(TEMPLATES_DIR, exist_ok=True)


@router.post("/create", response_model=TemplateResponse)
async def create(
    name: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    # Validate PDF
    if not file.filename.endswith(".pdf"):
        raise AppError("Only PDF files are allowed", status_code=400)

    # Save uploaded file with unique name into src/inputs/
    unique_name = f"{uuid.uuid4().hex}_{file.filename}"
    save_path = os.path.join(TEMPLATES_DIR, unique_name)

    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Extract fields using commonforms + pypdf
    # Store as simple list of field name strings — what Filler expects
    try:
        from commonforms import prepare_form
        from pypdf import PdfReader

        # Read real field names directly from original PDF
        # Use /T (internal name) as both key and label
        # Real names like "JobTitle", "Phone Number" are already human-readable
        reader = PdfReader(save_path)
        raw_fields = reader.get_fields() or {}

        fields = {}
        for internal_name, field_data in raw_fields.items():
            # Use /TU tooltip if available, otherwise prettify /T name
            label = None
            if isinstance(field_data, dict):
                label = field_data.get("/TU")
            if not label:
                # Prettify: "JobTitle" → "Job Title", "DATE7_af_date" → "Date"
                import re
                label = re.sub(r'([a-z])([A-Z])', r'\1 \2', internal_name)
                label = re.sub(r'_af_.*$', '', label)  # strip "_af_date" suffix
                label = label.replace('_', ' ').strip().title()
            fields[internal_name] = label

    except Exception as e:
        print(f"Field extraction failed: {e}")
        fields = []

    # Save to DB
    tpl = Template(name=name, pdf_path=save_path, fields=fields)
    return create_template(db, tpl)


@router.get("", response_model=list[TemplateResponse])
def list_templates(
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    return get_all_templates(db, limit=limit, offset=offset)


@router.get("/{template_id}", response_model=TemplateResponse)
def get_template_by_id(
    template_id: int,
    db: Session = Depends(get_db)
):
    from api.db.repositories import get_template
    tpl = get_template(db, template_id)
    if not tpl:
        raise AppError("Template not found", status_code=404)
    return tpl