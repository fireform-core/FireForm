from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlmodel import Session

from app.api.deps import get_db
from app.api.schemas.enums import JobStatus, JobType
from app.api.schemas.forms import (
    AsyncFormFill,
    AsyncFormFillResponse,
    AsyncJobSubmitResponse,
    JobResponse,
)
from app.core.errors.base import AppError
from app.db.repositories import create_job, get_job_by_uuid, get_template, update_job
from app.models import Job
from app.services import llm
from app.services.input import InputService
from app.tasks.fill import fill_form_task

router = APIRouter(tags=["jobs"])


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    job = get_job_by_uuid(db, job_id)
    if not job:
        raise AppError("Job not found", status_code=404)
    return JobResponse(
        job_id=job.job_id,
        job_type=job.job_type,
        status=job.status,
        progress_percent=job.progress_percent,
        result_url=job.result_url,
        error=job.error,
        created_at=job.created_at.isoformat() if job.created_at else None,
        updated_at=job.updated_at.isoformat() if job.updated_at else None,
    )


@router.post("/forms/jobs", response_model=AsyncFormFillResponse)
def submit_async_form_fill(form: AsyncFormFill, db: Session = Depends(get_db)):
    for tid in form.template_ids:
        if not get_template(db, tid):
            raise AppError(f"Template {tid} not found", status_code=404)

    transcript = InputService().resolve_transcript(db, form.input_id)
    # Checked here so a bad pick fails the request, not every queued job
    choice = llm.effective_registry(db).resolve(form.provider, form.model)

    jobs: list[AsyncJobSubmitResponse] = []
    for tid in form.template_ids:
        # Commit the job row before queueing the task, with the job's own id as
        # the task id: the worker looks the row up by task id and an idle worker
        # can start before a row inserted after delay() exists.
        job = Job(
            job_type=JobType.form_generation,
            template_id=tid,
            input_text=transcript,
            status=JobStatus.queued,
            provider=choice.provider,
            model=choice.model,
        )
        job.celery_task_id = job.job_id
        job = create_job(db, job)
        try:
            fill_form_task.apply_async(
                (tid, transcript, str(form.input_id), choice.model, choice.provider.value),
                task_id=job.celery_task_id,
            )
        except Exception as e:
            # Broker unreachable: mark this job row as failed so it is never
            # left stuck in "queued" forever.
            job.status = JobStatus.failed
            job.error = {"error_code": "QUEUE_UNAVAILABLE", "message": str(e)}
            job.updated_at = datetime.now(timezone.utc)
            update_job(db, job)

            # If earlier iterations already published jobs successfully, return
            # a 207 Multi-Status so the client can still discover and poll those
            # jobs.  A plain 503 would discard the accumulated job list and make
            # those jobs invisible, risking duplicate submissions on retry.
            error_msg = f"Could not queue fill job for template {tid}: {e}"
            if jobs:
                body = AsyncFormFillResponse(jobs=jobs, error=error_msg)
                return JSONResponse(status_code=207, content=body.model_dump())

            # Nothing was queued at all — a normal 503 is appropriate.
            raise AppError(
                error_msg,
                status_code=503,
                error_code="QUEUE_UNAVAILABLE",
            ) from e

        jobs.append(AsyncJobSubmitResponse(
            job_id=job.job_id,
            status=job.status,
            poll_url=f"/api/v1/jobs/{job.job_id}",
        ))

    return AsyncFormFillResponse(jobs=jobs)
