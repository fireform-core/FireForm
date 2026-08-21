import sys

from celery import Celery
from celery.signals import celeryd_init

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

@celeryd_init.connect
def _check_llm_config(**_kwargs):
    """Stop the worker on a bad LLM configuration, before it accepts any task.

    SystemExit rather than letting LLMConfigError travel: Celery catches
    anything deriving from Exception in a signal handler, logs it and carries
    on, so a raised config error would leave the worker running and picking up
    extractions it cannot serve. SystemExit is not an Exception, so it lands.
    """
    from app.services import llm

    try:
        llm.check_config()
    except llm.LLMConfigError as exc:
        print(f"FATAL: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc


celery_app.conf.include = [
    "app.tasks.fill",
    "app.tasks.purge",
    "app.tasks.transcribe",
    "app.tasks.extract",
    "app.tasks.detect_fields",
    "app.tasks.generate_forms",
]

# Optional Celery Beat schedule — runs purge_old_submissions once a day.
# Enable by running: celery -A app.core.celery beat
from celery.schedules import crontab  # noqa: E402
celery_app.conf.beat_schedule = {
    "daily-submission-purge": {
        "task": "purge_old_submissions",
        "schedule": crontab(hour=3, minute=0),  # 03:00 UTC daily
    },
}
