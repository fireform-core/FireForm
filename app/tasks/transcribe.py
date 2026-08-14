import logging
import wave
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from app.api.schemas.enums import InputStatus
from app.core.celery import celery_app
from app.core.config import AUDIO_CONTENT_TYPES
from app.db.database import get_session
from app.db.repositories import get_input, get_job_by_uuid, update_input, update_job
from app.services.whisper import call_whisper_asr

logger = logging.getLogger(__name__)


def _wav_duration(path: Path) -> float | None:
    """Return duration in seconds for a WAV file; None for all other formats or on error."""
    if path.suffix.lower() != ".wav":
        return None
    try:
        with wave.open(str(path)) as wf:
            return wf.getnframes() / wf.getframerate()
    except Exception:
        return None


def _fail_records(
    session,
    input_id: UUID,
    job_id_str: str,
    error_code: str,
    message: str,
) -> None:
    now = datetime.now(timezone.utc)
    record = get_input(session, input_id)
    if record:
        record.status = InputStatus.failed
        record.error_detail = message
        record.updated_at = now
        update_input(session, record)
    job = get_job_by_uuid(session, job_id_str)
    if job:
        job.status = "failed"
        job.error = {"error_code": error_code, "message": message}
        job.updated_at = now
        update_job(session, job)


@celery_app.task(name="transcribe_audio")
def transcribe_audio_task(input_id_str: str, audio_path: str, job_id_str: str) -> dict:
    session = next(get_session())
    input_id = UUID(input_id_str)
    try:
        input_record = get_input(session, input_id)
        job = get_job_by_uuid(session, job_id_str)

        # start: mark both records in-flight
        now = datetime.now(timezone.utc)
        input_record.status = InputStatus.transcribing
        input_record.updated_at = now
        update_input(session, input_record)

        job.status = "processing"
        job.updated_at = now
        update_job(session, job)

        # transcribe
        p = Path(audio_path)
        ext = p.suffix.lstrip(".")
        text = call_whisper_asr(p.read_bytes(), p.name, AUDIO_CONTENT_TYPES.get(ext, "audio/wav"))

        # success
        words = text.split()
        now = datetime.now(timezone.utc)
        input_record.status = InputStatus.ready
        input_record.transcript = text
        input_record.character_count = len(text)
        input_record.word_count = len(words)
        input_record.audio_duration_seconds = _wav_duration(p)
        input_record.updated_at = now
        update_input(session, input_record)

        job.status = "completed"
        job.result_url = f"/api/v1/input/{input_id_str}"
        job.updated_at = now
        update_job(session, job)

        return {"input_id": input_id_str, "job_id": job_id_str}

    except ConnectionError as exc:
        logger.exception("transcribe_audio_task: Whisper unavailable for input %s", input_id_str)
        _fail_records(session, input_id, job_id_str, "STT_UNAVAILABLE", str(exc))
        raise

    except RuntimeError as exc:
        logger.exception("transcribe_audio_task: transcription failed for input %s", input_id_str)
        _fail_records(session, input_id, job_id_str, "TRANSCRIPTION_FAILED", str(exc))
        raise

    finally:
        session.close()
