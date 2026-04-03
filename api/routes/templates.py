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
        reader = PdfReader(save_path)
        raw_fields = reader.get_fields() or {}

        fields = {}
        for internal_name, field_data in raw_fields.items():
            label = None
            if isinstance(field_data, dict):
                label = field_data.get("/TU")
            if not label:
                import re
                label = re.sub(r'([a-z])([A-Z])', r'\1 \2', internal_name)
                label = re.sub(r'_af_.*$', '', label)
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


@router.post("/{template_id}/scan")
async def scan_static_template(
    template_id: int,
    db: Session = Depends(get_db)
):
    """
    Uses Gemma 3 Vision model to scan a static/non-fillable PDF once,
    detect all blank fields by visual analysis, and store their coordinates
    in the Data Lake. Scan Once → Fill Forever.
    """
    print(f"\n\n🚨 [SCAN] Vision scan requested for template {template_id}\n")
    from api.db.repositories import get_template, get_template_coordinates, create_field_coordinates
    from api.db.models import FormFieldCoordinates

    tpl = get_template(db, template_id)
    if not tpl:
        raise AppError("Template not found", status_code=404)

    if not os.path.exists(tpl.pdf_path):
        raise AppError("Template PDF not found on disk", status_code=404)

    existing_coords = get_template_coordinates(db, template_id)
    if existing_coords:
        return {
            "status": "already_scanned",
            "message": "Template already has coordinate data",
            "fields_found": len(existing_coords)
        }

    import fitz
    from src.llm import LLM

    doc = fitz.open(tpl.pdf_path)
    if len(doc) == 0:
        raise AppError("PDF has no pages", status_code=400)

    # Render page 1 as a high-res image for the vision model
    page = doc[0]
    pix = page.get_pixmap(dpi=150)
    img_bytes = pix.tobytes("png")
    doc.close()

    llm = LLM()
    try:
        vision_fields = await llm.async_vision_scan_fields(img_bytes)
        print(f"[VISION] Found {len(vision_fields)} fields on static template.")
    except Exception as e:
        raise AppError(f"Vision scan failed: {e}", status_code=500)

    if not vision_fields:
        return {"status": "no_fields_found", "message": "Vision model found no fields."}

    # Save coordinates into DB
    stored_coords = []
    semantic_fields = {}

    for vf in vision_fields:
        c = FormFieldCoordinates(
            template_id=template_id,
            field_label=vf.get("label", "unknown_field"),
            page_number=0,
            x=float(vf.get("x", 0)),
            y=float(vf.get("y", 0)),
            width=float(vf.get("w", vf.get("width", 20))),
            height=float(vf.get("h", vf.get("height", 5))),
            field_type=vf.get("type", "text")
        )
        stored_coords.append(c)
        semantic_fields[c.field_label] = c.field_label.replace("_", " ").title()

    create_field_coordinates(db, stored_coords)

    if not tpl.fields or len(tpl.fields) == 0:
        tpl.fields = semantic_fields
        db.add(tpl)
        db.commit()

    return {
        "status": "success",
        "message": f"Vision scan complete — {len(stored_coords)} fields mapped.",
        "fields": semantic_fields
    }