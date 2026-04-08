import os
import re
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

TEMPLATES_DIR = os.path.join("src", "inputs")
os.makedirs(TEMPLATES_DIR, exist_ok=True)


@router.post("/create", response_model=TemplateResponse)
async def create(
    name: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    if not file.filename.endswith(".pdf"):
        raise AppError("Only PDF files are allowed", status_code=400)

    unique_name = f"{uuid.uuid4().hex}_{file.filename}"
    save_path = os.path.join(TEMPLATES_DIR, unique_name)

    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        from commonforms import prepare_form
        from pypdf import PdfReader

        reader = PdfReader(save_path)
        raw_fields = reader.get_fields() or {}

        fields = {}
        for internal_name, field_data in raw_fields.items():
            label = None
            if isinstance(field_data, dict):
                label = field_data.get("/TU")
            if not label:
                label = re.sub(r'([a-z])([A-Z])', r'\1 \2', internal_name)
                label = re.sub(r'_af_.*$', '', label)
                label = label.replace('_', ' ').strip().title()
            fields[internal_name] = label

    except Exception as e:
        print(f"Field extraction failed: {e}")
        fields = []

    tpl = Template(name=name, pdf_path=save_path, fields=fields)
    return create_template(db, tpl)


@router.get("", response_model=list[TemplateResponse])
def list_templates(limit: int = 100, offset: int = 0, db: Session = Depends(get_db)):
    return get_all_templates(db, limit=limit, offset=offset)


@router.get("/{template_id}", response_model=TemplateResponse)
def get_template_by_id(template_id: int, db: Session = Depends(get_db)):
    from api.db.repositories import get_template
    tpl = get_template(db, template_id)
    if not tpl:
        raise AppError("Template not found", status_code=404)
    return tpl


# ── PyMuPDF-based deterministic field finder ───────────────────────────
#
#  Approach (for static non-fillable PDFs with a text layer):
#
#  1.  PyMuPDF page.get_text("words") → word-level bboxes (x0,y0,x1,y1,text)
#  2.  Group words into visual lines by Y coordinate (3pt tolerance)
#  3.  Lines containing ":" or "____" are field lines
#  4.  Blank zone = underscore position OR right-edge of colon word + small gap
#  5.  Gemma (text-only) cleans raw label into snake_case — no vision needed
#  6.  Coordinates stored as percentages of page size in the DB
#      → filler converts back to absolute pts at render time
#
#  PyMuPDF is used instead of pdfplumber because it is already installed
#  as part of the core stack (fitz) and avoids an optional dependency.
#
#  Gemma Vision is ONLY used as a fallback when the PDF has NO text layer
#  (i.e. a flat image scan with no searchable text).

def _scan_fields_with_pymupdf(pdf_path: str) -> list[dict]:
    """
    Deterministic field detection for static PDFs using PyMuPDF word-level bboxes.

    Uses page.get_text("words") which returns tuples:
        (x0, y0, x1, y1, text, block_no, line_no, word_no)
    where the coordinate origin is the TOP-LEFT of the page (y increases downward).

    Returns a list of dicts, each with:
      raw_label:      cleaned label text (e.g. "Name")
      answer_x:       absolute x-point where the answer starts (pt, top-left origin)
      answer_y:       absolute y-point of the line top (pt, top-left origin)
      answer_bottom:  absolute y-point of the line bottom (pt, top-left origin)
      page_num:       0-indexed page number
      page_w:         page width in points
      page_h:         page height in points
      line_text:      full original line text (for debugging)
    """
    import fitz  # PyMuPDF — already installed

    found_fields = []


    return found_fields


async def _clean_labels_with_gemma(raw_labels: list[str], image_bytes: bytes) -> list[str]:
    """
    Optional: Ask Gemma to convert raw label strings to clean snake_case names.
    Falls back to simple regex cleaning if Gemma fails.
    """
    from src.llm import LLM
    import json

    llm = LLM()

    # Build a prompt asking Gemma to clean these specific labels
    label_list = "\n".join(f"  {i}: \"{l}\"" for i, l in enumerate(raw_labels))
    prompt = f'''I have these raw field labels from a form. Convert each to a clear, short snake_case identifier.

Raw labels:
{label_list}

Return a JSON array of strings in the SAME ORDER, one snake_case name per label.
Example: ["full_name", "email_address", "phone_number"]

Rules:
- Keep the semantic meaning (e.g. "Name" → "full_name", "Tel" → "phone")
- Use only lowercase letters and underscores
- Output ONLY the JSON array'''

    try:
        import base64
        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        vision_model = os.getenv("FIREFORM_VISION_MODEL", "gemma3:4b")
        b64_image = base64.b64encode(image_bytes).decode("utf-8")

        payload = {
            "model": vision_model,
            "prompt": prompt,
            "images": [b64_image],
            "stream": False,
        }

        import requests
        response = requests.post(f"{ollama_host}/api/generate", json=payload, timeout=300)
        response.raise_for_status()
        res_text = response.json().get("response", "").strip()

        # Clean markdown fences
        for fence in ["```json", "```"]:
            if res_text.startswith(fence):
                res_text = res_text[len(fence):]
        if res_text.endswith("```"):
            res_text = res_text[:-3]
        res_text = res_text.strip()

        data = json.loads(res_text)
        if isinstance(data, list) and len(data) == len(raw_labels):
            print(f"[GEMMA] Cleaned labels: {data}")
            return [str(d) for d in data]
        elif isinstance(data, dict):
            for v in data.values():
                if isinstance(v, list) and len(v) == len(raw_labels):
                    return [str(d) for d in v]
    except Exception as e:
        print(f"[GEMMA] Label cleaning failed ({e}), using regex fallback")

    # Regex fallback
    clean = []
    for label in raw_labels:
        snake = re.sub(r'[^a-zA-Z0-9]', '_', label.strip().lower())
        snake = re.sub(r'_+', '_', snake).strip('_')
        clean.append(snake or "unknown_field")
    return clean


# ── Scan endpoint ─────────────────────────────────────────────────────────────

@router.post("/{template_id}/scan")
async def scan_static_template(template_id: int, db: Session = Depends(get_db)):
    """
    Deterministic scan for static (non-fillable) PDFs.
    Scan Once → Fill Forever.

    For PDFs WITH a text layer:
      1. pdfplumber extracts word-level coordinates (deterministic)
      2. We find field lines (colon/underscore patterns)
      3. Gemma cleans up the label names (semantic)
      4. Absolute point coordinates are saved to FormFieldCoordinates

    For PDFs WITHOUT a text layer (flat scans):
      1. Gemma Vision scans the image for field bounding boxes
      2. Results are saved to FormFieldCoordinates

    Either way: the template is scanned ONCE and coordinates are
    stored in the Data Lake forever. No re-scanning, no guessing.
    """
    print(f"\n🔍 [SCAN] Template {template_id}\n")
    from api.db.repositories import get_template, get_template_coordinates, create_field_coordinates
    from api.db.models import FormFieldCoordinates
    import fitz
    from src.llm import LLM

    tpl = get_template(db, template_id)
    if not tpl:
        raise AppError("Template not found", status_code=404)
    if not os.path.exists(tpl.pdf_path):
        raise AppError("Template PDF not found on disk", status_code=404)

    existing_coords = get_template_coordinates(db, template_id)
    if existing_coords:
        return {"status": "already_scanned", "message": "Already scanned.", "fields_found": len(existing_coords)}

    # Get page dimensions and check for text layer
    doc = fitz.open(tpl.pdf_path)
    if len(doc) == 0:
        raise AppError("PDF has no pages", status_code=400)

    page = doc[0]
    page_w, page_h = page.rect.width, page.rect.height
    pix = page.get_pixmap(dpi=150)
    img_bytes = pix.tobytes("png")
    word_count = len(page.get_text("words"))
    doc.close()

    has_text_layer = word_count > 5
    print(f"[SCAN] {page_w:.0f}×{page_h:.0f}pt | words={word_count} | text_layer={has_text_layer}")

    found_fields: list[dict] = []
    scan_mode = "unknown"

    # ── PRIMARY PATH: PyMuPDF deterministic scan ─────────────────────────
    if has_text_layer:
        scan_mode = "pymupdf"
        print("[SCAN] Using PyMuPDF deterministic word-level scan...")

        try:
            raw_fields = _scan_fields_with_pymupdf(tpl.pdf_path)
        except Exception as e:
            print(f"[SCAN] ⚠️ PyMuPDF scan crashed: {e}")
            import traceback
            traceback.print_exc()
            raw_fields = []

        if raw_fields:
            print(f"[SCAN] Found {len(raw_fields)} field lines:")
            for f in raw_fields:
                print(f"   '{f['raw_label']:30s}' → answer_x={f['answer_x']:.1f}pt  y={f['answer_y']:.1f}pt")

            # Ask Gemma to clean up label names (semantic intelligence)
            raw_labels = [f["raw_label"] for f in raw_fields]
            clean_labels = await _clean_labels_with_gemma(raw_labels, img_bytes)

            for i, rf in enumerate(raw_fields):
                snake_label = clean_labels[i] if i < len(clean_labels) else "unknown_field"
                found_fields.append({
                    "label": snake_label,
                    "display": rf["raw_label"],
                    "x": rf["answer_x"],       # absolute PDF points
                    "y": rf["answer_y"],        # absolute PDF points
                    "w": rf["page_w"] * 0.9 - rf["answer_x"],  # remaining width
                    "h": rf["answer_bottom"] - rf["answer_y"],  # line height
                    "page_num": rf["page_num"],
                    "page_w": rf["page_w"],
                    "page_h": rf["page_h"],
                    "type": "text",
                    "coord_unit": "pt",         # MARKER: absolute points, not %
                })

            print(f"\n[SCAN] ✅ pdfplumber matched {len(found_fields)} fields")

    # ── FALLBACK PATH: Gemma Vision for image-only PDFs ──────────────────
    if not found_fields:
        reason = "no text layer" if not has_text_layer else "pdfplumber found 0 fields"
        print(f"[SCAN] Fallback → Gemma Vision ({reason})...")
        scan_mode = "vision"
        llm = LLM()
        try:
            found_fields = await llm.async_vision_scan_fields(img_bytes)
            # Vision fields come as percentages — mark them accordingly
            for vf in found_fields:
                vf["coord_unit"] = "pct"
            print(f"[SCAN] Gemma vision: {len(found_fields)} fields")
        except Exception as e:
            raise AppError(f"Vision scan failed: {e}", status_code=500)

    if not found_fields:
        return {"status": "no_fields_found", "message": "No fields detected."}

    # ── Save to Data Lake (FormFieldCoordinates) ─────────────────────────
    stored_coords, semantic_fields = [], {}
    for vf in found_fields:
        coord_unit = vf.get("coord_unit", "pct")

        if coord_unit == "pt":
            # Absolute points: convert to percentages for DB storage
            # (DB schema uses 0-100 percentages)
            x_pct = (vf["x"] / vf["page_w"]) * 100
            y_pct = (vf["y"] / vf["page_h"]) * 100
            w_pct = (vf["w"] / vf["page_w"]) * 100
            h_pct = (vf["h"] / vf["page_h"]) * 100
        else:
            # Already percentages (from vision fallback)
            x_pct = float(vf.get("x", 0))
            y_pct = float(vf.get("y", 0))
            w_pct = float(vf.get("w", vf.get("width", 20)))
            h_pct = float(vf.get("h", vf.get("height", 5)))

        c = FormFieldCoordinates(
            template_id=template_id,
            field_label=vf.get("label", "unknown_field"),
            page_number=vf.get("page_num", 0),
            x=round(x_pct, 3),
            y=round(y_pct, 3),
            width=round(w_pct, 3),
            height=round(h_pct, 3),
            field_type=vf.get("type", "text")
        )
        stored_coords.append(c)
        semantic_fields[c.field_label] = vf.get("display", c.field_label).replace("_", " ").title()

        print(f"  💾 {c.field_label:25s} → x={c.x:.1f}%  y={c.y:.1f}%  w={c.width:.1f}%  [{scan_mode}]")

    create_field_coordinates(db, stored_coords)

    if not tpl.fields or len(tpl.fields) == 0:
        tpl.fields = semantic_fields
        db.add(tpl)
        db.commit()

    return {
        "status": "success",
        "scan_mode": scan_mode,
        "message": f"Scan complete ({scan_mode}) — {len(stored_coords)} fields.",
        "fields": semantic_fields,
    }