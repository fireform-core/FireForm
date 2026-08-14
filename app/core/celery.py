from celery import Celery
from celery.schedules import crontab

celery_app = Celery("fireform")

celery_app.conf.beat_schedule = {
    "daily-submission-purge": {
        "task": "purge_old_submissions",
        "schedule": crontab(hour=3, minute=0),  # 03:00 UTC daily
    },
}
