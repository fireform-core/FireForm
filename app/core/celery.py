from celery import Celery

from app.core.config import CELERY_BROKER_URL, CELERY_RESULT_BACKEND

celery_app = Celery(
    "fireform",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    result_expires=86400,
)

celery_app.conf.include = ["app.tasks.fill", "app.tasks.purge", "app.tasks.transcribe"]

# Optional Celery Beat schedule — runs purge_old_submissions once a day.
# Enable by running: celery -A app.core.celery beat
from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    "daily-submission-purge": {
        "task": "purge_old_submissions",
        "schedule": crontab(hour=3, minute=0),  # 03:00 UTC daily
    },
}
