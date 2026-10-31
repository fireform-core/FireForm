from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, JSONResponse
from sqlmodel import Session

from app.api.deps import get_db
from app.api.schemas.common import AsyncJobResponse
from app.api.schemas.enums import JobStatus, JobType, OutputFormat
from app.api.schemas.reporting import (
    GenerateReportRequest,
    PeriodicReport,
    ReportProgressResponse,
)
from app.core.config import API_PREFIX
from app.core.errors.base import AppError
from app.db.repositories import create_job, create_report, get_report, update_job, update_report
from app.models import Job, Report
from app.services.reporting import ReportingService
from app.tasks.report import generate_periodic_report

router = APIRouter(prefix="/reports", tags=["reporting"])


@router.post(
    "/generate",
    response_model=AsyncJobResponse,
    status_code=202,
    responses={
        202: {"description": "Report generation job accepted", "model": AsyncJobResponse},
    },
)
def generate_report(body: GenerateReportRequest, db: Session = Depends(get_db)):
    # Validate request bounds and check future date
    ReportingService().validate_and_compute_bounds(body)

    # 1. Create Job record
    job = Job(
        job_type=JobType.report_generation,
        status=JobStatus.queued,
    )
    job.celery_task_id = job.job_id
    job = create_job(db, job)

    # 2. Create Report record
    report = Report(
        period_type=body.period_type,
        year=body.year,
        month=body.month,
        quarter=body.quarter,
        output_format=body.format,
        status=JobStatus.queued,
        job_id=UUID(job.job_id),
    )
    report = create_report(db, report)

    # 3. Dispatch background task
    try:
        generate_periodic_report.apply_async(
            (str(report.report_id),), task_id=job.celery_task_id
        )
    except Exception as e:
        job.status = JobStatus.failed
        job.error = {"error_code": "QUEUE_UNAVAILABLE", "message": str(e)}
        job.updated_at = datetime.now(timezone.utc)
        update_job(db, job)

        report.status = JobStatus.failed
        report.updated_at = datetime.now(timezone.utc)
        update_report(db, report)

        raise AppError(
            f"Could not queue report generation job: {e}",
            status_code=503,
            error_code="QUEUE_UNAVAILABLE",
        ) from e

    return AsyncJobResponse(
        job_id=job.job_id,
        job_type=job.job_type,
        status=JobStatus.processing,
        estimated_seconds=30,
        poll_url=f"{API_PREFIX}/reports/{report.report_id}",
        report_id=str(report.report_id),
    )


@router.get(
    "/{report_id}",
    responses={
        200: {
            "description": "Generated report (PDF binary or JSON)",
            "content": {
                "application/pdf": {"schema": {"type": "string", "format": "binary"}},
                "application/json": {"schema": {"$ref": "#/components/schemas/PeriodicReport"}},
            },
        },
        202: {
            "description": "Report still being generated",
            "model": ReportProgressResponse,
        },
    },
)
def get_report_by_id(report_id: UUID, db: Session = Depends(get_db)):
    report = get_report(db, report_id)
    if not report:
        raise AppError(
            f"Report {report_id} not found",
            status_code=404,
            error_code="REPORT_NOT_FOUND",
        )

    if report.status in (JobStatus.queued, JobStatus.processing):
        return JSONResponse(
            status_code=202,
            content={
                "message": "Report generation is still in progress",
                "status": "processing",
                "retry_after_seconds": 10,
            },
        )

    if report.status == JobStatus.failed:
        raise AppError(
            "Report generation failed",
            status_code=500,
            error_code="REPORT_FAILED",
        )

    # Completed
    if report.output_format == OutputFormat.pdf:
        if not report.pdf_path or not Path(report.pdf_path).exists():
            raise AppError(
                "Generated PDF report file not found",
                status_code=500,
                error_code="PDF_NOT_FOUND",
            )
        filename = Path(report.pdf_path).name
        return FileResponse(
            path=report.pdf_path,
            media_type="application/pdf",
            filename=filename,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # OutputFormat.json or OutputFormat.both
    return PeriodicReport.model_validate(report.json_data)
