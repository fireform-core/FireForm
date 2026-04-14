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


# ── PyMuPDF-based deterministic field finder ───────────────────────
#
#  PATH 1 — Text-layer PDFs  (typed Word docs, digital PDFs)
#  PATH 2 — Image-based PDFs (screenshots pasted into Word, scanned docs)
#         → Tesseract OCR on the rendered page image
#  PATH 3 — Final fallback   (Gemma Vision, for exotic/complex cases)
#
#  Gemma is used ONLY for:
#    a) Cleaning raw label text to snake_case (both paths)
#    b) Final fallback vision scan (path 3 only)
#  Gemma NEVER estimates coordinates.

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


def _scan_fields_with_tesseract(pdf_path: str, dpi: int = 200) -> list[dict]:
    """
    PATH 2: Deterministic field detection for image-based static PDFs.

    Renders each page to a raster image (via PyMuPDF) then runs Tesseract OCR
    with pytesseract.image_to_data() to get word-level bounding boxes.

    Coordinate system:
      Tesseract returns pixel coordinates relative to the rendered image.
      We convert: px → PDF points via  pt = px * (72 / dpi)
      Then store as percentages of page size (same as PyMuPDF path).

    Uses the same colon / underscore field detection logic as the text-layer path,
    so a single downstream pipeline handles both PDF types identically.

    Requires: pytesseract and Tesseract binary (v5+ recommended).
    """
    import fitz
    import pytesseract
    from PIL import Image
    import io

    # Point pytesseract at the Tesseract binary (Windows path)
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

    found_fields = []
    doc = fitz.open(pdf_path)
    print(f"[TESSERACT] Opened '{pdf_path}' — {len(doc)} page(s) at {dpi} DPI")

    for page_num in range(len(doc)):
        page = doc[page_num]
        pw_pt = page.rect.width    # page width  in PDF points
        ph_pt = page.rect.height   # page height in PDF points

        # Render page to image
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        img_w, img_h = img.size
        print(f"[TESSERACT] Page {page_num}: rendered {img_w}x{img_h}px (PDF: {pw_pt:.0f}x{ph_pt:.0f}pt)")

        # Preprocess image for better OCR on low-quality/scanned PDFs
        # Grayscale + contrast enhancement helps Tesseract significantly
        from PIL import ImageOps, ImageFilter
        img_gray = img.convert("L")                   # grayscale
        img_enhanced = ImageOps.autocontrast(img_gray, cutoff=2)  # boost contrast

        # Run Tesseract OCR — returns word-level data
        ocr_data = pytesseract.image_to_data(
            img_enhanced,
            output_type=pytesseract.Output.DICT,
            config="--psm 6"   # assume uniform block of text
        )

        # Build word dicts, filtering out empty/low-confidence tokens
        # Tesseract bbox: left, top, width, height (all in pixels)
        words = []
        n = len(ocr_data["text"])
        for i in range(n):
            txt  = ocr_data["text"][i].strip()
            conf = int(ocr_data["conf"][i])
            # conf == -1 → non-word token (block/para/line level), skip
            # conf >= 0  → actual OCR word (0=very uncertain, 100=certain)
            if not txt or conf < 0:
                continue
            px_left = ocr_data["left"][i]
            px_top  = ocr_data["top"][i]
            px_w    = ocr_data["width"][i]
            px_h    = ocr_data["height"][i]

            # Convert pixel coords → PDF points
            scale = 72.0 / dpi
            x0 = px_left * scale
            y0 = px_top  * scale
            x1 = (px_left + px_w) * scale
            y1 = (px_top  + px_h) * scale

            words.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1, "text": txt})

        print(f"[TESSERACT] Page {page_num}: {len(words)} confident words")
        for w in words[:12]:
            print(f"  word '{w['text']:20s}' x0={w['x0']:6.1f} y0={w['y0']:6.1f}")
        if len(words) > 12:
            print(f"  ... and {len(words) - 12} more")

        # ── Group words into visual lines (same logic as PyMuPDF path) ────
        Y_TOL = 4   # slightly larger tolerance for OCR jitter
        sorted_words = sorted(words, key=lambda w: (w["y0"], w["x0"]))

        lines: list[list[dict]] = []
        current_line: list[dict] = []
        current_y: float | None = None

        for w in sorted_words:
            if current_y is None or abs(w["y0"] - current_y) <= Y_TOL:
                current_line.append(w)
                if current_y is None:
                    current_y = w["y0"]
            else:
                if current_line:
                    lines.append(current_line)
                current_line = [w]
                current_y = w["y0"]
        if current_line:
            lines.append(current_line)

        print(f"[TESSERACT] Grouped into {len(lines)} visual lines")
        for idx, lw in enumerate(lines):
            lt = " ".join(w["text"] for w in lw)
            print(f"  line {idx:02d}: '{lt[:90]}'")

        # ── Identical field detection logic as PyMuPDF path ─────────────
        for line_words in lines:
            line_words = sorted(line_words, key=lambda w: w["x0"])
            full_text = " ".join(w["text"] for w in line_words)

            has_colon       = ":" in full_text
            has_underscores = "_" * 4 in full_text or full_text.count("_") >= 4

            if not (has_colon or has_underscores):
                continue

            # Skip header lines with content after colon
            if has_colon and not has_underscores:
                colon_pos = full_text.find(":")
                after_colon = full_text[colon_pos + 1:].strip()
                if after_colon and not after_colon.startswith("_"):
                    label_part = full_text[:colon_pos].strip().lower()
                    HEADER_WORDS = {"title", "form", "section", "page", "date", "version", "revision"}
                    if any(hw in label_part for hw in HEADER_WORDS):
                        continue

            label_text    = full_text.strip()
            answer_x: float | None = None
            answer_y      = min(w["y0"] for w in line_words)
            answer_bottom = max(w["y1"] for w in line_words)

            if has_underscores:
                for w in line_words:
                    if "_" * 4 in w["text"]:
                        answer_x = w["x0"]
                        answer_bottom = w["y1"]
                        label_parts = [lw["text"] for lw in line_words if lw["x0"] < w["x0"]]
                        if label_parts:
                            label_text = " ".join(label_parts)
                        break

            if answer_x is None and has_colon:
                for w in line_words:
                    if ":" in w["text"]:
                        answer_x = w["x1"] + 2
                        label_parts = []
                        for lw in line_words:
                            label_parts.append(lw["text"])
                            if ":" in lw["text"]:
                                break
                        label_text = " ".join(label_parts)
                        break

            if answer_x is None:
                answer_x = line_words[-1]["x1"] + 2

            clean_label = re.sub(r'^[\d\.\)\s]+', '', label_text)
            clean_label = clean_label.rstrip(': _\n').strip()

            if not clean_label:
                continue

            found_fields.append({
                "raw_label":     clean_label,
                "answer_x":      round(answer_x, 2),
                "answer_y":      round(answer_y, 2),
                "answer_bottom": round(answer_bottom, 2),
                "page_num":      page_num,
                "page_w":        round(pw_pt, 2),
                "page_h":        round(ph_pt, 2),
                "line_text":     full_text.strip(),
            })
            print(f"  [FIELD] '{clean_label:25s}' answer_x={answer_x:.1f}pt  y0={answer_y:.1f}pt")

    doc.close()
    print(f"[TESSERACT] Done — {len(found_fields)} field(s) found")
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
      1. PyMuPDF extracts word-level coordinates (deterministic)
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

    raw_fields: list[dict] = []
    found_fields: list[dict] = []
    scan_mode = "unknown"

    # ── PATH 1: PyMuPDF — text-layer PDFs ────────────────────────────────
    if has_text_layer:
        scan_mode = "pymupdf"
        print("[SCAN] PATH 1: PyMuPDF deterministic word-level scan...")
        try:
            raw_fields = _scan_fields_with_pymupdf(tpl.pdf_path)
        except Exception as e:
            print(f"[SCAN] ⚠️ PyMuPDF crashed: {e}")
            import traceback; traceback.print_exc()
            raw_fields = []

    # ── PATH 2: Tesseract OCR — image-based PDFs ─────────────────────────
    if not raw_fields:
        reason = "no text layer" if not has_text_layer else "PyMuPDF found 0 fields"
        print(f"[SCAN] PATH 2: Tesseract OCR ({reason})...")
        scan_mode = "tesseract"
        try:
            raw_fields = _scan_fields_with_tesseract(tpl.pdf_path)
        except Exception as e:
            print(f"[SCAN] ⚠️ Tesseract crashed: {e}")
            import traceback; traceback.print_exc()
            raw_fields = []

    # ── Shared: clean labels with Gemma (text→text only, no vision) ───────
    if raw_fields:
        print(f"[SCAN] {len(raw_fields)} raw field(s) — asking Gemma to clean labels...")
        raw_labels  = [f["raw_label"] for f in raw_fields]
        clean_labels = await _clean_labels_with_gemma(raw_labels, img_bytes)

        for i, rf in enumerate(raw_fields):
            snake_label = clean_labels[i] if i < len(clean_labels) else "unknown_field"
            found_fields.append({
                "label":      snake_label,
                "display":    rf["raw_label"],
                "x":          rf["answer_x"],
                "y":          rf["answer_y"],
                "w":          rf["page_w"] * 0.9 - rf["answer_x"],
                "h":          rf["answer_bottom"] - rf["answer_y"],
                "page_num":   rf["page_num"],
                "page_w":     rf["page_w"],
                "page_h":     rf["page_h"],
                "type":       "text",
                "coord_unit": "pt",
            })
        print(f"[SCAN] ✅ {scan_mode} → {len(found_fields)} fields with exact coords")

    # ── PATH 3: Gemma Vision — last resort only ───────────────────────────
    if not found_fields:
        print("[SCAN] PATH 3: Gemma Vision (last resort — both deterministic paths failed)...")
        scan_mode = "vision"
        llm = LLM()
        try:
            found_fields = await llm.async_vision_scan_fields(img_bytes)
            for vf in found_fields:
                vf["coord_unit"] = "pct"  # Gemma returns guessed percentages
            print(f"[SCAN] Gemma vision: {len(found_fields)} fields")
        except Exception as e:
            raise AppError(f"All scan paths failed: {e}", status_code=500)

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