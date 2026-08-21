"""Form generation service.

Owns the write path for POST /forms/generate: validates the incident and
every requested template, splits templates into ready/not-ready via the
readiness engine (extraction_readiness.gaps_for), creates one Form row per
queued template, creates the batch Job, and dispatches the fill worker.
Mirrors ExtractionService.start_extraction's shape. The route stays a thin
HTTP handler and calls straight into here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlmodel import Session

from app.api.schemas.enums import FormStatus
from app.api.schemas.form_generation import GenerateFormsOptions, GenerateFormsRequest
from app.core.errors.base import AppError
from app.db.repositories import (
    create_generated_form,
    create_job,
    get_incident,
    update_form,
    update_job,
)
from app.models import Form, Job
from app.services.extraction_readiness import gaps_for
from app.services.form_templates import require_template
from app.tasks.generate_forms import generate_forms_batch_task


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


class FormGenerationService:
    def start_generation(self, session: Session, request: GenerateFormsRequest) -> GenerationResult:
        incident = get_incident(session, request.incident_id)
        if incident is None:
            raise AppError(
                f"Incident {request.incident_id} not found",
                status_code=404,
                error_code="INCIDENT_NOT_FOUND",
            )

        # Resolve every requested template before writing anything: a bad
        # template_id 404s cleanly instead of leaving a partial batch behind.
        templates = [require_template(session, tid) for tid in request.template_ids]

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
            raise AppError(
                "No templates were selected and none are ready",
                status_code=422,
                error_code="NO_FORMS_TO_GENERATE",
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
