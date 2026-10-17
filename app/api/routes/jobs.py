from fastapi import APIRouter, Depends
from sqlmodel import Session
from app.api.deps import get_db
from app.api.schemas.forms import JobResponse
from app.db.repositories import get_job_by_uuid, list_active_jobs, list_recent_jobs
from app.core.errors.base import AppError

router = APIRouter(tags=["jobs"])

@router.get("/jobs", response_model=list[JobResponse])
def list_jobs(db: Session = Depends(get_db)):
    jobs = list_recent_jobs(db, limit=20)
    return jobs

@router.get("/jobs/active", response_model=list[JobResponse])
def list_active_jobs_api(db: Session = Depends(get_db)):
    jobs = list_active_jobs(db)
    return jobs

@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    job = get_job_by_uuid(db, job_id)
    if not job:
        raise AppError.not_found("Job not found")
    return job