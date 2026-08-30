"""Celery glue for the batch form-fill worker.

All the work lives in app/services/form_fill_worker.py. This is only the
broker entry point: open a session, run the batch, close the session. Mirrors
app/tasks/extract.py's split — not app/tasks/fill.py, the legacy prototype task.
"""

import logging
from uuid import UUID

from app.core.celery import celery_app
from app.db.database import get_session
from app.services.form_fill_worker import run_batch_fill

logger = logging.getLogger(__name__)


@celery_app.task(name="generate_forms_batch")
def generate_forms_batch_task(batch_id_str: str, job_id_str: str) -> dict:
    """Fill every queued form in one batch."""
    session = next(get_session())
    try:
        return run_batch_fill(session, UUID(batch_id_str), job_id_str)
    finally:
        session.close()
