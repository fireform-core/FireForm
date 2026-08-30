"""Celery glue for template field detection.

The work lives in app/services/template_detection.py. Detection runs here
rather than in the request because commonforms loads a vision model and can
take minutes on a scanned form. The upload row already holds the stored PDF
and its page geometry, so the editor is usable the whole time this runs.
"""

import logging
from uuid import UUID

from app.core.celery import celery_app
from app.db.database import get_session

logger = logging.getLogger(__name__)


@celery_app.task(name="detect_template_fields")
def detect_template_fields_task(upload_id_str: str, job_id_str: str | None = None) -> dict:
    """Detect the fields of one uploaded template PDF."""
    # Imported inside the task so the API process never pulls the detection
    # stack in just by importing this module.
    from app.services.template_detection import run_detection

    session = next(get_session())
    try:
        return run_detection(session, UUID(upload_id_str), job_id_str)
    finally:
        session.close()
