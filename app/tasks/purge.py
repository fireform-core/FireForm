"""Celery beat task: purge form submissions older than RETENTION_PERIOD_DAYS.

Runs automatically if Celery Beat is configured. Can also be triggered manually
via the API endpoint POST /api/v1/forms/purge.
"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.celery import celery_app
from app.core.config import RETENTION_PERIOD_DAYS
from app.core.paths import PROJECT_ROOT
from app.db.database import get_session
from app.db.repositories import delete_form_submission
from app.models import FormSubmission
from sqlmodel import select

logger = logging.getLogger(__name__)


def _safe_delete_file(file_path: str) -> bool:
    """Delete a project-relative or absolute file safely. Returns True if deleted."""
    try:
        candidate = Path(file_path)
        if not candidate.is_absolute():
            candidate = (PROJECT_ROOT / candidate).resolve()
        else:
            candidate = candidate.resolve()

        # Safety: must stay inside project root
        if candidate != PROJECT_ROOT and PROJECT_ROOT not in candidate.parents:
            logger.warning("Skipping file outside project root: %s", candidate)
            return False

        if candidate.exists() and candidate.is_file():
            candidate.unlink()
            return True
    except Exception as exc:
        logger.error("Failed to delete file %s: %s", file_path, exc)
    return False


@celery_app.task(name="purge_old_submissions")
def purge_old_submissions(retention_days: int | None = None) -> dict:
    """Delete form submissions (and associated output PDFs) older than retention_days.

    Args:
        retention_days: Number of days to retain data. Defaults to the
            RETENTION_PERIOD_DAYS environment variable (default: 30).

    Returns:
        dict with purged_count and retention_days_used.
    """
    days = retention_days if retention_days is not None else RETENTION_PERIOD_DAYS
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    logger.info("Purging submissions older than %s days (cutoff: %s)", days, cutoff)

    session = next(get_session())
    purged_count = 0
    files_deleted = 0

    try:
        statement = select(FormSubmission).where(FormSubmission.created_at < cutoff)
        submissions = list(session.exec(statement))

        for sub in submissions:
            if sub.output_pdf_path:
                if _safe_delete_file(sub.output_pdf_path):
                    files_deleted += 1
            delete_form_submission(session, sub)
            purged_count += 1

        logger.info(
            "Purge complete: removed %d submissions and %d output files",
            purged_count,
            files_deleted,
        )
        return {
            "purged_count": purged_count,
            "files_deleted": files_deleted,
            "retention_days_used": days,
        }

    except Exception as exc:
        logger.exception("purge_old_submissions task failed: %s", exc)
        raise
    finally:
        session.close()
