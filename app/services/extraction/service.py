"""Extraction service.

Owns the write path that turns a ready input into a queued extraction: it
creates the extraction row, creates the async job, and dispatches the worker.
The route stays a thin HTTP handler and calls straight into here.

The request's deployment defaults and hints are not stored on the extraction
row, they only shape this one run, so they travel to the worker as task
arguments.
"""

from datetime import datetime, timezone

from sqlmodel import Session

from app.api.schemas.enums import ExtractionStatus
from app.api.schemas.extraction import ExtractionDefaults, ExtractionHints
from app.db.repositories import create_extraction, create_job, update_job
from app.models import Extraction, Job
from app.tasks.extract import extract_task


def _as_dict(value: ExtractionDefaults | ExtractionHints | None) -> dict:
    """Task arguments have to be plain JSON, so models go over as dicts."""
    return value.model_dump(exclude_none=True) if value is not None else {}


class ExtractionService:
    def start_extraction(
        self,
        session: Session,
        input_id,
        model_override: str | None = None,
        defaults: ExtractionDefaults | None = None,
        hints: ExtractionHints | None = None,
    ) -> tuple[Extraction, Job]:
        """Create the extraction row and job, then dispatch the worker.

        The extraction starts in ``processing`` so a poll right after the 202
        sees the in-flight shape. Mirrors the transcription flow: the job row is
        created first with a known job_id, dispatched, then its celery_task_id
        is backfilled once the broker returns a task id.
        """
        now = datetime.now(timezone.utc)
        extraction = Extraction(
            input_id=input_id,
            status=ExtractionStatus.processing,
            started_at=now,
            model_used=model_override,
            created_at=now,
            updated_at=now,
        )
        extraction = create_extraction(session, extraction)

        job = Job(celery_task_id="", job_type="extraction", status="queued", model=model_override)
        job = create_job(session, job)

        result = extract_task.delay(
            str(extraction.extract_id),
            job.job_id,
            _as_dict(defaults),
            _as_dict(hints),
        )
        job.celery_task_id = result.id
        job = update_job(session, job)

        return extraction, job
