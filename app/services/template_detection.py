"""Field detection for an uploaded template PDF.

commonforms finds the boxes, this turns them into editable template fields.
Widget rectangles come out of the PDF already in points with a bottom-left
origin, which is exactly what `TemplateFieldLayout` stores, so no coordinate
conversion happens anywhere on the backend. The editor converts to pixels for
display and back again on save.

Detection is best effort by design. A box whose label cannot be read still
comes back with its geometry, and geometry alone is a fine starting point for
someone drawing the rest by hand.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from pypdf import PdfReader, PdfWriter
from sqlmodel import Session

from app.api.schemas.enums import DetectionStatus, FieldSource, TemplateFieldType
from app.api.schemas.templates import (
    DraftField,
    MappingSuggestion,
    PageGeometry,
    TemplateField,
    TemplateFieldLayout,
)
from app.core.config import (
    MAPPING_AUTO_APPLY_SCORE,
    MAPPING_SUGGESTION_FLOOR,
    MAX_MAPPING_SUGGESTIONS,
)
from app.core.logging import get_logger
from app.db.repositories import (
    get_job_by_uuid,
    get_template_upload,
    update_job,
    update_template_upload,
)
from app.services import field_catalog

logger = get_logger(__name__)

_NAME_CLEANUP = re.compile(r"[^a-z0-9]+")

# How far from a box a piece of text can sit and still be taken as its label.
# Both are in points: roughly two characters of slack to the left, and a little
# over one line height above.
_LABEL_GAP_LEFT = 160.0
_LABEL_GAP_ABOVE = 26.0


# ---------------------------------------------------------------------------
# Reading the PDF
# ---------------------------------------------------------------------------
def read_pages(pdf_path: str | Path) -> list[PageGeometry]:
    """Per-page size in PDF points, index 0 first."""
    reader = PdfReader(str(pdf_path))
    pages = []
    for index, page in enumerate(reader.pages):
        box = page.mediabox
        pages.append(
            PageGeometry(
                page=index,
                width=float(box.width),
                height=float(box.height),
            )
        )
    return pages


def _text_positions(page) -> list[tuple[str, float, float]]:
    """Every text fragment on the page as (text, x, y) in points.

    pypdf hands the text matrix to the visitor, whose last two entries are the
    drawing position. Fragments are kept whole rather than merged into lines:
    form labels are nearly always drawn in one go, and merging risks gluing a
    neighbouring column onto the label.
    """
    found: list[tuple[str, float, float]] = []

    def visit(text, _cm, tm, _font_dict, _font_size):
        cleaned = text.strip()
        if cleaned:
            found.append((cleaned, float(tm[4]), float(tm[5])))

    try:
        page.extract_text(visitor_text=visit)
    except Exception as exc:
        # A PDF whose content stream will not parse still has usable widgets.
        logger.warning("could not read text for label detection: %s", exc)
    return found


def _nearest_label(
    layout: TemplateFieldLayout, texts: list[tuple[str, float, float]]
) -> str | None:
    """The text most likely to be this box's label.

    Printed forms put the label to the left of the box, or directly above it.
    Left wins when both exist, because a label above is often the column
    heading for a whole run of boxes.
    """
    top = layout.y + layout.height

    left = [
        (layout.x - x, text)
        for text, x, y in texts
        if x < layout.x
        and layout.x - x <= _LABEL_GAP_LEFT
        and layout.y - 2 <= y <= top + 2
    ]
    if left:
        return min(left)[1]

    above = [
        (y - top, text)
        for text, x, y in texts
        if top <= y <= top + _LABEL_GAP_ABOVE
        and layout.x - 4 <= x <= layout.x + layout.width
    ]
    if above:
        return min(above)[1]
    return None


def _widgets(pdf_path: str | Path) -> list[tuple[TemplateFieldLayout, str | None, list]]:
    """Every form widget in the PDF as (layout, widget name, page texts).

    The page index lives on the layout, so it is not repeated in the tuple.
    """
    reader = PdfReader(str(pdf_path))
    out = []
    for index, page in enumerate(reader.pages):
        annotations = page.get("/Annots")
        if not annotations:
            continue
        texts = _text_positions(page)
        # MediaBox does not have to start at the origin. Subtracting its corner
        # keeps every stored coordinate relative to the page the editor draws.
        origin_x = float(page.mediabox.left)
        origin_y = float(page.mediabox.bottom)

        for annotation in annotations:
            try:
                obj = annotation.get_object()
            except Exception:
                continue
            if obj.get("/Subtype") != "/Widget":
                continue
            rect = obj.get("/Rect")
            if not rect or len(rect) != 4:
                continue
            x0, y0, x1, y1 = (float(v) for v in rect)
            width, height = abs(x1 - x0) or 1.0, abs(y1 - y0) or 1.0
            layout = TemplateFieldLayout(
                page=index,
                x=max(min(x0, x1) - origin_x, 0),
                y=max(min(y0, y1) - origin_y, 0),
                width=width,
                height=height,
            )
            name = obj.get("/T")
            out.append((layout, str(name) if name else None, texts))

    # Reading order: top of the page down, then left to right.
    out.sort(key=lambda item: (item[0].page, -item[0].y, item[0].x))
    return out


# ---------------------------------------------------------------------------
# Turning widgets into draft fields
# ---------------------------------------------------------------------------
def suggest_mappings(label: str | None) -> list[MappingSuggestion]:
    """Ranked contract paths for a detected label, best first.

    Returns nothing when the label is missing or nothing scores above the
    floor. An empty list is the honest answer, and the editor's search box
    covers it.
    """
    if not label:
        return []

    query = field_catalog.normalize_label(label)
    hits = field_catalog.search(query, limit=MAX_MAPPING_SUGGESTIONS)
    return [
        MappingSuggestion(
            path=entry.path,
            label=entry.label,
            field_type=entry.field_type,
            section=entry.section,
            description=entry.description,
            score=round(score, 4),
        )
        for entry, score in hits
        if score is not None and score >= MAPPING_SUGGESTION_FLOOR
    ]


def _field_name(raw: str | None, used: set[str], position: int) -> str:
    """A unique, slug-shaped name for a detected box."""
    base = _NAME_CLEANUP.sub("_", (raw or "").lower()).strip("_")
    if not base:
        base = f"field_{position}"
    name = base
    suffix = 2
    while name in used:
        name = f"{base}_{suffix}"
        suffix += 1
    used.add(name)
    return name


def _apply_suggestion(
    field: TemplateField, suggestions: list[MappingSuggestion]
) -> TemplateField:
    """Pre-apply the top suggestion when it clears the auto-apply mark."""
    if not suggestions or suggestions[0].score < MAPPING_AUTO_APPLY_SCORE:
        return field

    top = suggestions[0]
    update = {"source": FieldSource.schema, "incident_mapping": top.path}

    entry = next((e for e in field_catalog.catalog() if e.path == top.path), None)
    if entry and entry.enum_values:
        update["field_type"] = TemplateFieldType.enum
        update["allowed_values"] = list(entry.enum_values)

    return field.model_copy(update=update)


def _drafts_from_widgets(widgets: list) -> list[DraftField]:
    used: set[str] = set()
    drafts: list[DraftField] = []

    for position, (layout, widget_name, texts) in enumerate(widgets, start=1):
        label = _nearest_label(layout, texts)
        # A widget's own name is often the best clue a fillable PDF gives
        # ("incident_number"), so it stands in when no text sits near the box.
        # `detected_label` still reports only what was read off the page.
        suggestions = suggest_mappings(label or widget_name)
        field = TemplateField(
            field_name=_field_name(widget_name or label, used, position),
            field_type=TemplateFieldType.string,
            # Nothing is assumed about an unmapped box: manual means a person
            # types the value, which is always safe to change to something else.
            source=FieldSource.manual,
            required=False,
            layout=layout,
        )
        drafts.append(
            DraftField(
                field=_apply_suggestion(field, suggestions),
                detected_label=label,
                suggestions=suggestions,
            )
        )
    return drafts


def build_draft_fields(pdf_path: str | Path) -> list[DraftField]:
    """Read a PDF's form widgets and turn each into a draft field."""
    return _drafts_from_widgets(_widgets(pdf_path))


def _pad_with_blank_page(pdf_path: Path) -> Path:
    """Write a copy of a one-page PDF with a blank second page appended.

    commonforms cannot read a single-page document. It wraps the detector's
    output a second time when the page count is 1 (inference.py), and the
    rfdetr versions it now installs with already hand back a list, so the run
    dies with "'list' object has no attribute 'with_nms'". One blank page keeps
    us off that branch. Detections on the padding are dropped afterwards.
    """
    reader = PdfReader(str(pdf_path))
    page = reader.pages[0]
    writer = PdfWriter()
    writer.add_page(page)
    writer.add_blank_page(width=page.mediabox.width, height=page.mediabox.height)

    padded = pdf_path.with_name(f"{pdf_path.stem}_padded.pdf")
    with padded.open("wb") as handle:
        writer.write(handle)
    return padded


def detect_fields(pdf_path: str | Path) -> list[DraftField]:
    """Run commonforms over a PDF, then draft a field per detected box.

    A PDF that already carries form widgets is used as-is. commonforms only
    has to run on flat scans, and it is the slow part.
    """
    # Imported here, not at module scope: the Controller pulls in the whole
    # detection stack, which is far too heavy for an API process to import.
    from app.services.controller import Controller

    pdf_path = Path(pdf_path)
    widgets = _widgets(pdf_path)
    if widgets:
        logger.info("%s already has form widgets, skipping detection", pdf_path)
        return _drafts_from_widgets(widgets)

    padded = None
    if len(PdfReader(str(pdf_path)).pages) == 1:
        padded = _pad_with_blank_page(pdf_path)
        logger.info("%s is one page, padding it for commonforms", pdf_path)

    fillable_path = None
    try:
        fillable_path = Path(Controller().prepare_fillable(str(padded or pdf_path)))
        drafts = build_draft_fields(fillable_path)
    finally:
        # Both files are scratch. The boxes live in the draft from here on, and
        # the upload the user later registers points at the original PDF.
        if padded:
            padded.unlink(missing_ok=True)
        if fillable_path:
            fillable_path.unlink(missing_ok=True)

    if padded:
        # Nothing should land on the blank page, but a stray box there would
        # otherwise become a field on a page the real PDF does not have.
        drafts = [d for d in drafts if d.field.layout and d.field.layout.page == 0]
    return drafts


# ---------------------------------------------------------------------------
# The background run
# ---------------------------------------------------------------------------
def _finish_job(session: Session, job_id: str | None, status: str, error: dict | None = None) -> None:
    if not job_id:
        return
    job = get_job_by_uuid(session, job_id)
    if not job:
        return
    job.status = status
    if status == "completed":
        job.progress_percent = 100
    job.error = error
    job.updated_at = datetime.now(timezone.utc)
    update_job(session, job)


def run_detection(session: Session, upload_id: UUID, job_id: str | None = None) -> dict:
    """Detect an upload's fields and write the draft back. Returns a summary.

    Failure is not exceptional here. The PDF and its page geometry are already
    stored, so a detection that falls over still leaves the editor able to draw
    every box by hand, and that is what the failed status tells it to do.
    """
    upload = get_template_upload(session, upload_id)
    if upload is None:
        logger.warning("upload %s vanished before detection ran", upload_id)
        _finish_job(
            session,
            job_id,
            "failed",
            {"error_code": "UPLOAD_NOT_FOUND", "message": "Upload no longer exists"},
        )
        return {"upload_id": str(upload_id), "status": "failed"}

    job = get_job_by_uuid(session, job_id) if job_id else None
    if job:
        job.status = "processing"
        job.updated_at = datetime.now(timezone.utc)
        update_job(session, job)

    now = datetime.now(timezone.utc)
    try:
        drafts = detect_fields(upload.pdf_path)
    except Exception as exc:
        logger.exception("field detection failed for upload %s", upload_id)
        upload.status = DetectionStatus.failed
        upload.detection_error = str(exc)
        upload.updated_at = now
        update_template_upload(session, upload)
        _finish_job(
            session, job_id, "failed", {"error_code": "DETECTION_FAILED", "message": str(exc)}
        )
        return {"upload_id": str(upload_id), "status": "failed"}

    upload.detected_fields = [draft.model_dump(mode="json") for draft in drafts]
    upload.status = DetectionStatus.completed
    upload.detection_error = None
    upload.updated_at = now
    update_template_upload(session, upload)

    if job:
        job.result_url = f"/api/v1/templates/pdf/{upload_id}"
        update_job(session, job)
    _finish_job(session, job_id, "completed")

    return {
        "upload_id": str(upload_id),
        "status": "completed",
        "detected_fields": len(drafts),
    }
