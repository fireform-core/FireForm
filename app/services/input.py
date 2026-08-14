from datetime import date, datetime, timezone

from sqlmodel import Session

from app.api.schemas.enums import InputStatus, InputType
from app.core.config import AUDIO_DIR
from app.db.repositories import create_input, create_job, update_job
from app.models import Input, Job
from app.tasks.transcribe import transcribe_audio_task


class InputService:
    def build_voice_input(
        self,
        original_filename: str,
        station_id: str | None = None,
        responder_badge: str | None = None,
        incident_date_hint: date | None = None,
    ) -> Input:
        now = datetime.now(timezone.utc)
        return Input(
            input_type=InputType.voice,
            status=InputStatus.queued,
            original_filename=original_filename,
            station_id=station_id,
            responder_badge=responder_badge,
            incident_date_hint=incident_date_hint,
            created_at=now,
            updated_at=now,
        )

    def process_voice_upload(
        self,
        session: Session,
        audio_content: bytes,
        ext: str,
        filename: str,
        station_id: str | None,
        responder_badge: str | None,
        incident_date_hint: date | None,
    ) -> tuple[Input, Job]:
        record = self.build_voice_input(
            original_filename=filename,
            station_id=station_id,
            responder_badge=responder_badge,
            incident_date_hint=incident_date_hint,
        )
        record = create_input(session, record)

        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        audio_path = AUDIO_DIR / f"{record.input_id}.{ext}"
        audio_path.write_bytes(audio_content)

        # Create Job, dispatch, and backfill celery_task_id.
        # On any failure after the file write, remove the orphaned audio file.
        try:
            job = Job(celery_task_id="", job_type="transcription", status="queued")
            job = create_job(session, job)
            result = transcribe_audio_task.delay(str(record.input_id), str(audio_path), job.job_id)
            job.celery_task_id = result.id
            job = update_job(session, job)
        except Exception:
            if audio_path.exists():
                audio_path.unlink()
            raise

        return record, job

    def build_text_input(
        self,
        narrative: str,
        station_id: str | None = None,
        responder_badge: str | None = None,
        incident_date_hint: date | None = None,
    ) -> Input:
        words = narrative.split()
        if len(words) < 10:
            raise ValueError("Must contain at least 10 words")
        now = datetime.now(timezone.utc)
        return Input(
            input_type=InputType.text,
            status=InputStatus.ready,
            transcript=narrative,
            character_count=len(narrative),
            word_count=len(words),
            station_id=station_id,
            responder_badge=responder_badge,
            incident_date_hint=incident_date_hint,
            created_at=now,
            updated_at=now,
        )
