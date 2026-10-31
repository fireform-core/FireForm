import logging
from datetime import datetime, timezone
from uuid import UUID

from app.api.schemas.enums import JobStatus
from app.core.celery import celery_app
from app.db.database import get_session
from app.db.repositories import get_job_by_celery_id, get_report, update_job, update_report
from app.services.reporting import ReportingService

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="generate_periodic_report")
def generate_periodic_report(self, report_id_str: str) -> dict:
    session = next(get_session())
    try:
        report_uuid = UUID(report_id_str)
        job = get_job_by_celery_id(session, self.request.id)
        if job:
            job.status = JobStatus.processing
            job.progress_percent = 20
            job.updated_at = datetime.now(timezone.utc)
            update_job(session, job)

        report = get_report(session, report_uuid)
        if report:
            report.status = JobStatus.processing
            report.updated_at = datetime.now(timezone.utc)
            update_report(session, report)

        # Run report generation pipeline
        ReportingService().generate_report(session, report_uuid)

        # Mark completed
        report = get_report(session, report_uuid)
        if report:
            report.status = JobStatus.completed
            report.updated_at = datetime.now(timezone.utc)
            update_report(session, report)

        if job:
            job.status = JobStatus.completed
            job.progress_percent = 100
            job.result_url = f"/api/v1/reports/{report_id_str}"
            job.updated_at = datetime.now(timezone.utc)
            update_job(session, job)

        return {"job_id": job.job_id if job else None, "report_id": report_id_str}

    except Exception as e:
        logger.exception("generate_periodic_report failed")
        job = get_job_by_celery_id(session, self.request.id)
        if job:
            job.status = JobStatus.failed
            job.error = {"error_code": "TASK_FAILED", "message": str(e)}
            job.updated_at = datetime.now(timezone.utc)
            update_job(session, job)

        report = get_report(session, UUID(report_id_str))
        if report:
            report.status = JobStatus.failed
            report.updated_at = datetime.now(timezone.utc)
            update_report(session, report)
        raise
    finally:
        session.close()
