"""Batch form-fill worker.

Fills every queued Form in a batch: resolve each template field's value from
the incident contract (extraction_readiness.resolve), draw the placed ones
onto a ReportLab overlay at their TemplateFieldLayout coordinates, merge that
overlay onto the template PDF with pypdf, and save the result. Each form is
independently try/excepted — one bad form marks that form failed and moves
on, it never sinks the batch or the job.

Mirrors app/services/extraction/worker.py's shape (a plain function taking a
session, called by the thin Celery task in app/tasks/generate_forms.py).

Not to be confused with the legacy app/services/filler.py, which fills
AcroForm widgets by name in visual order — this draws free text at explicit
layout coordinates onto a flat PDF and merges the overlay on top. Layout
coordinates are bottom-left-origin PDF points, the same space ReportLab's
canvas uses natively, so no flip is applied.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from uuid import UUID

from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import HexColor
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from sqlmodel import Session

from app.api.schemas.enums import FormStatus, TextAlign
from app.api.schemas.templates import TemplateField
from app.core.config import DATA_DIR, FORMS_OUTPUT_DIR
from app.core.logging import get_logger
from app.db.repositories import (
    get_form_template,
    get_incident,
    get_job_by_uuid,
    list_forms_by_batch,
    update_form,
    update_job,
)
from app.models import Form, FormTemplate
from app.services.extraction_readiness import gaps_for, resolve
from app.services.form_templates import resolve_template_pdf

logger = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _format_value(value) -> str | None:
    """A drawable string for a resolved field value, or None to skip drawing."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (dict, list)):
        # A composite contract value has no single sane rendering on a form box.
        return None
    text = str(value).strip()
    return text or None


def _fit_text(text: str, font: str, size: float, max_width: float) -> str:
    """Truncate with an ellipsis if the text is wider than its box."""
    if stringWidth(text, font, size) <= max_width:
        return text
    while text and stringWidth(f"{text}…", font, size) > max_width:
        text = text[:-1]
    return f"{text}…" if text else ""


def _draw_field(c: canvas.Canvas, field: TemplateField, value: object) -> None:
    layout = field.layout
    text = _format_value(value)
    if not text:
        return

    c.setFont(layout.font, layout.font_size)
    c.setFillColor(HexColor(layout.color))
    text = _fit_text(text, layout.font, layout.font_size, layout.width)

    if layout.align == TextAlign.center:
        c.drawCentredString(layout.x + layout.width / 2, layout.y, text)
    elif layout.align == TextAlign.right:
        c.drawRightString(layout.x + layout.width, layout.y, text)
    else:
        c.drawString(layout.x, layout.y, text)


def _build_overlay(
    template_pdf_path: Path, fields: list[TemplateField], contract: dict, form_type: str
) -> PdfReader:
    """One ReportLab page per template page, sized to match, with each placed
    field's resolved value drawn at its layout coordinates."""
    template_reader = PdfReader(str(template_pdf_path))
    page_count = len(template_reader.pages)

    by_page: dict[int, list[TemplateField]] = defaultdict(list)
    for field in fields:
        if field.layout is not None and 0 <= field.layout.page < page_count:
            by_page[field.layout.page].append(field)

    buf = BytesIO()
    c = canvas.Canvas(buf)
    for page_index in range(page_count):
        box = template_reader.pages[page_index].mediabox
        c.setPageSize((float(box.width), float(box.height)))
        for field in by_page.get(page_index, []):
            _draw_field(c, field, resolve(contract, field, form_type))
        # showPage() advances to a fresh page — only between pages, never
        # after the last one, or save() would emit a trailing blank page.
        if page_index < page_count - 1:
            c.showPage()
    c.save()
    buf.seek(0)
    return PdfReader(buf)


def _merge_overlay(template_pdf_path: Path, overlay: PdfReader) -> PdfWriter:
    """Merge the overlay onto a writer already cloned from the template.

    Merging happens on pages already attached to the writer (via
    clone_from), not on bare PdfReader pages added afterward — pypdf
    deprecated merge-then-add in favor of this order.
    """
    writer = PdfWriter(clone_from=str(template_pdf_path))
    for index, page in enumerate(writer.pages):
        if index < len(overlay.pages):
            page.merge_page(overlay.pages[index], over=True)
    return writer


def _summary(contract: dict, template: FormTemplate) -> dict:
    gaps = gaps_for(contract, template)
    total = len(template.fields or [])
    blank = len(gaps.missing_required) + len(gaps.missing_recommended)
    return {
        "total_form_fields": total,
        "fields_filled": total - blank,
        "fields_blank": blank,
        "coverage_percent": gaps.coverage_percent,
    }


def fill_one(session: Session, form: Form) -> None:
    """Fill a single queued form. Raises on any failure — the batch loop
    below decides how to record that against the Form row."""
    form.status = FormStatus.generating
    form.updated_at = _now()
    update_form(session, form)

    incident = get_incident(session, form.incident_id)
    if incident is None:
        raise ValueError(f"incident {form.incident_id} no longer exists")

    template = get_form_template(session, form.template_id)
    if template is None:
        raise ValueError(f"template {form.template_id} no longer exists")

    contract = incident.incident_contract or {}
    fields = [TemplateField.model_validate(entry) for entry in template.fields or []]
    agency_fields = {f.field_name: resolve(contract, f, template.form_type) for f in fields}

    template_pdf_path = resolve_template_pdf(session, form.template_id)
    overlay = _build_overlay(template_pdf_path, fields, contract, template.form_type)
    writer = _merge_overlay(template_pdf_path, overlay)

    FORMS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = FORMS_OUTPUT_DIR / f"{form.form_id}.pdf"
    with output_path.open("wb") as handle:
        writer.write(handle)

    form.pdf_path = str(output_path.relative_to(DATA_DIR))
    form.pdf_ready = True
    form.json_data = agency_fields
    form.json_ready = True
    form.field_mapping_summary = _summary(contract, template)
    form.status = FormStatus.completed
    form.completed_at = _now()
    form.updated_at = _now()
    update_form(session, form)


def run_batch_fill(session: Session, batch_id: UUID, job_id: str) -> dict:
    """Fill every queued form in a batch. Each form is independently
    try/excepted: one failure marks that form failed and moves on — it never
    sinks the batch or the job, per design."""
    forms = list_forms_by_batch(session, batch_id)
    job = get_job_by_uuid(session, job_id)

    if job:
        job.status = "processing"
        job.updated_at = _now()
        update_job(session, job)

    completed = 0
    failed = 0
    for index, form in enumerate(forms, start=1):
        try:
            fill_one(session, form)
            completed += 1
        except Exception:
            logger.exception("form %s (batch %s) failed to generate", form.form_id, batch_id)
            form.status = FormStatus.failed
            form.updated_at = _now()
            update_form(session, form)
            failed += 1

        if job:
            job.progress_percent = round(100 * index / len(forms)) if forms else 100
            job.updated_at = _now()
            update_job(session, job)

    if job:
        job.status = "completed"
        job.progress_percent = 100
        job.result_url = f"/api/v1/forms/batch/{batch_id}"
        job.updated_at = _now()
        update_job(session, job)

    logger.info(
        "batch %s finished: %d/%d forms completed, %d failed",
        batch_id, completed, len(forms), failed,
    )
    return {"batch_id": str(batch_id), "completed": completed, "failed": failed}
