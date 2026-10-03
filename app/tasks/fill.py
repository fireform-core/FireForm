import logging
from datetime import datetime, timezone
from uuid import UUID

from app.core.celery import celery_app
from app.db.database import get_session
from app.db.repositories import get_job_by_celery_id, get_template, update_job
from app.services.form import FormService

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="fill_form")
def fill_form_task(self, template_id: int, input_text: str, input_id_str: str, model: str | None = None):
    session = next(get_session())
    try:
        job = get_job_by_celery_id(session, self.request.id)
        if not job:
            raise RuntimeError(f"No job row for celery task {self.request.id}")

        job.status = "processing"
        job.progress_percent = 10
        job.updated_at = datetime.now(timezone.utc)
        update_job(session, job)

        template = get_template(session, template_id)
        if not template:
            raise ValueError(f"Template {template_id} not found")

        submission = FormService().fill_and_persist(
            session, template, input_text, UUID(input_id_str), model
        )

        job.status = "completed"
        job.progress_percent = 100
        job.result_url = f"/api/v1/forms/{submission.id}/download"
        job.updated_at = datetime.now(timezone.utc)
        update_job(session, job)

        return {"job_id": job.job_id, "result_url": job.result_url}

    except Exception as e:
        logger.exception("fill_form_task failed")
        job = get_job_by_celery_id(session, self.request.id)
        if job:
            job.status = "failed"
            job.error = {"error_code": "TASK_FAILED", "message": str(e)}
            job.updated_at = datetime.now(timezone.utc)
            update_job(session, job)
        raise
    finally:
        session.close()
