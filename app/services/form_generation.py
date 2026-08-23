"""Form generation service.

Owns the write path for POST /forms/generate: validates the incident and
every requested template, splits templates into ready/not-ready via the
readiness engine (extraction_readiness.gaps_for), creates one Form row per
queued template, creates the batch Job, and dispatches the fill worker.
Mirrors ExtractionService.start_extraction's shape. The route stays a thin
HTTP handler and calls straight into here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from sqlmodel import Session

from app.api.schemas.enums import FormStatus, TemplateStatus
from app.api.schemas.form_generation import GenerateFormsOptions, GenerateFormsRequest
from app.core.config import DATA_DIR
from app.core.errors.base import AppError
from app.db.repositories import (
    create_generated_form,
    create_job,
    get_form_template,
    get_incident,
    list_form_templates,
    update_form,
    update_job,
)
from app.models import Form, FormTemplate, Job
from app.services.extraction_readiness import gaps_for
from app.services.form_templates import require_template
from app.tasks.generate_forms import generate_forms_batch_task

# Anything outside this set is replaced in a download filename. Incident
# numbers are free text typed by a responder, so they can carry slashes,
# spaces or quotes, none of which belong in a Content-Disposition header.
# Dots go too: the only one in the name should be the one before "pdf".
_UNSAFE_IN_FILENAME = re.compile(r"[^A-Za-z0-9_-]+")


@dataclass
class SkippedTemplate:
    template_id: UUID
    form_type: str
    reason: str


@dataclass
class GenerationResult:
    batch_id: UUID
    incident_id: UUID
    queued: list[Form] = field(default_factory=list)
    skipped: list[SkippedTemplate] = field(default_factory=list)
    job: Job | None = None


def _skip_reason(gaps) -> str:
    """One representative reason, per the agreed format. A template can be
    missing more than one required field; this names the first one, the same
    way the contract's own example names a single field."""
    gap = gaps.missing_required[0]
    return f"Not ready: {gap.field_name} ({gap.source.value}) has no value"


def _slug(value: str) -> str:
    return _UNSAFE_IN_FILENAME.sub("-", value).strip("-")


def _pdf_filename(form: Form, incident_number: str | None) -> str:
    number = _slug(incident_number) if incident_number else ""
    if not number:
        return f"{form.form_id}.pdf"
    return f"{_slug(form.form_type)}_{number}.pdf"


def download_filename(session: Session, form: Form) -> str:
    """The name a downloaded PDF is saved under.

    "{form_type}_{incident_number}.pdf", the same name the batch zip gives its
    entries, so a form downloaded on its own and the same form pulled out of a
    batch land as one file. Incident numbers are optional and are only assigned
    once the department has one, so the form id stands in when it is missing.
    """
    incident = get_incident(session, form.incident_id)
    return _pdf_filename(form, incident.incident_number if incident else None)


def form_version(session: Session, form: Form) -> str | None:
    """The version of the template the form was generated from.

    Read live off the template rather than stamped on the form: templates are
    versioned in place, so this reports the registry's current version, not the
    one in force at fill time.
    """
    template = get_form_template(session, form.template_id)
    return template.version if template else None


def batch_state(forms: list[Form]) -> str:
    """processing, completed or failed, derived from the batch's Form rows.

    There is no Batch table, so both the status endpoint and the zip download
    read the batch's state from the same place. Per design a single failed form
    does not fail the batch: it reads completed as long as every form reached a
    terminal state and at least one succeeded, and the per-form list still shows
    which ones failed.
    """
    total = len(forms)
    completed = sum(1 for f in forms if f.status == FormStatus.completed)
    failed = sum(1 for f in forms if f.status == FormStatus.failed)
    if completed + failed < total:
        return "processing"
    return "failed" if failed == total else "completed"


def resolve_form_pdf(form: Form) -> Path | None:
    """The form's PDF on disk, or None if it is not there to serve.

    pdf_path is stored relative to the data directory, so a value that climbs
    out of it is refused rather than read. Single downloads turn a None into a
    404; the batch zip just leaves that form out.
    """
    if not form.pdf_ready or not form.pdf_path:
        return None
    path = (DATA_DIR / form.pdf_path).resolve()
    if not path.is_relative_to(DATA_DIR) or not path.is_file():
        return None
    return path


def batch_pdfs(session: Session, forms: list[Form]) -> list[tuple[str, Path]]:
    """Every finished PDF in the batch, as (name in the archive, path on disk).

    Forms that failed, or whose file has gone missing under the data directory,
    are left out rather than failing the whole download. One incident lookup
    covers the batch because every form in it is filled from the same incident.
    """
    if not forms:
        return []

    incident = get_incident(session, forms[0].incident_id)
    number = incident.incident_number if incident else None

    entries: list[tuple[str, Path]] = []
    for form in forms:
        if form.status != FormStatus.completed:
            continue
        path = resolve_form_pdf(form)
        if path is not None:
            entries.append((_pdf_filename(form, number), path))
    return entries


def batch_zip(session: Session, batch_id: UUID, forms: list[Form]) -> tuple[bytes, str]:
    """The batch's PDFs as one zip, with the name to serve it under.

    Built in memory: a batch is one incident's report pack, so it is a handful
    of PDFs rather than something worth spooling to disk.
    """
    entries = batch_pdfs(session, forms)
    incident = get_incident(session, forms[0].incident_id) if forms else None
    number = _slug(incident.incident_number) if incident and incident.incident_number else ""

    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for name, path in entries:
            archive.write(path, arcname=name)

    return buffer.getvalue(), f"fireform_batch_{number or batch_id}.zip"


class FormGenerationService:
    def _candidates(self, session: Session, request: GenerateFormsRequest) -> list[FormTemplate]:
        """The templates this request is about, before readiness is considered.

        An explicit selection is taken as given, including a legacy or draft
        template the user deliberately picked. With no selection the candidates
        are the active templates, the same set the readiness matrix offers on
        the selection screen, so "generate everything ready" cannot pull in a
        retired form nobody chose.

        Every requested template is resolved before anything is written: a bad
        template_id 404s cleanly instead of leaving a partial batch behind.
        """
        if request.template_ids is not None:
            return [require_template(session, tid) for tid in request.template_ids]
        return [t for t in list_form_templates(session) if t.status == TemplateStatus.active]

    def start_generation(self, session: Session, request: GenerateFormsRequest) -> GenerationResult:
        incident = get_incident(session, request.incident_id)
        if incident is None:
            raise AppError(
                f"Incident {request.incident_id} not found",
                status_code=404,
                error_code="INCIDENT_NOT_FOUND",
            )

        templates = self._candidates(session, request)

        options = request.options or GenerateFormsOptions()
        contract = incident.incident_contract or {}
        batch_id = uuid4()
        now = datetime.now(timezone.utc)
        result = GenerationResult(batch_id=batch_id, incident_id=incident.incident_id)

        for template in templates:
            gaps = gaps_for(contract, template)

            if not gaps.ready and not options.force_partial:
                result.skipped.append(
                    SkippedTemplate(
                        template_id=template.template_id,
                        form_type=template.form_type,
                        reason=_skip_reason(gaps),
                    )
                )
                continue

            form = Form(
                template_id=template.template_id,
                incident_id=incident.incident_id,
                batch_id=batch_id,
                form_type=template.form_type,
                status=FormStatus.queued,
                created_at=now,
                updated_at=now,
            )
            result.queued.append(create_generated_form(session, form))

        if not result.queued:
            # Two ways to end up here, and the caller needs to tell them apart:
            # a selection whose every template turned out to be blocked, or no
            # selection at all with nothing in the registry ready to generate.
            raise AppError(
                "None of the selected templates are ready"
                if request.template_ids is not None
                else "No templates were selected and none are ready",
                status_code=422,
                error_code="NO_FORMS_TO_GENERATE",
                detail={"skipped": [s.reason for s in result.skipped]},
            )

        job = Job(celery_task_id="", job_type="batch_form_generation", status="queued")
        try:
            job = create_job(session, job)
            task_result = generate_forms_batch_task.delay(str(batch_id), job.job_id)
            job.celery_task_id = task_result.id
            job = update_job(session, job)
        except Exception:
            # Dispatch failed after the Form rows were already committed —
            # mirrors InputService.process_voice_upload's cleanup discipline:
            # nothing is left claiming to be queued with no job behind it.
            failed_at = datetime.now(timezone.utc)
            for queued_form in result.queued:
                queued_form.status = FormStatus.failed
                queued_form.updated_at = failed_at
                update_form(session, queued_form)
            raise

        result.job = job
        return result
