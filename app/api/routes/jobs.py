from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.deps import get_db
from app.api.schemas.forms import (
    AsyncFormFill,
    AsyncFormFillResponse,
    AsyncJobSubmitResponse,
    JobResponse,
)
from app.core.errors.base import AppError
from app.db.repositories import create_job, get_job_by_uuid, get_template
from app.models import Job
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

    jobs: list[AsyncJobSubmitResponse] = []
    for tid in form.template_ids:
        result = fill_form_task.delay(tid, form.input_text, form.model)
        job = Job(
            celery_task_id=result.id,
            job_type="form_generation",
            template_id=tid,
            input_text=form.input_text,
            status="queued",
            model=form.model,
        )
        job = create_job(db, job)
        jobs.append(AsyncJobSubmitResponse(
            job_id=job.job_id,
            status=job.status,
            poll_url=f"/api/v1/jobs/{job.job_id}",
        ))

    return AsyncFormFillResponse(jobs=jobs)
