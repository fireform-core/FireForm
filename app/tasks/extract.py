"""Celery glue for the extraction worker.

All the work lives in app/services/extraction/worker.py. This is only the
broker entry point: open a session, run the extraction, close the session.
"""

import logging
from uuid import UUID

from app.core.celery import celery_app
from app.db.database import get_session
from app.services.extraction.worker import run_extraction

logger = logging.getLogger(__name__)


@celery_app.task(name="extract_incident")
def extract_task(
    extract_id_str: str,
    job_id_str: str,
    defaults: dict | None = None,
    hints: dict | None = None,
) -> dict:
    """Run the chunked extraction for one queued extraction row."""
    session = next(get_session())
    try:
        return run_extraction(session, UUID(extract_id_str), job_id_str, defaults, hints)
    finally:
        session.close()
