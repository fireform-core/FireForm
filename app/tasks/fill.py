import logging
from datetime import datetime, timezone

from app.core.celery import celery_app
from app.db.database import get_session
from app.db.repositories import (
    create_form,
    get_job_by_celery_id,
    get_template,
    update_job,
)
from app.models import FormSubmission
from app.services.controller import Controller

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="fill_form")
def fill_form_task(self, template_id: int, input_text: str, model: str | None = None):
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

        controller = Controller()
        path = controller.fill_form(
            user_input=input_text,
            fields=template.fields,
            pdf_form_path=template.pdf_path,
            model=model,
        )

        submission = FormSubmission(
            template_id=template_id,
            input_text=input_text,
            output_pdf_path=path,
        )
        create_form(session, submission)

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
