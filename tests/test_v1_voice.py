"""Tests for POST /api/v1/input/voice (endpoint) and transcribe_audio_task (task unit).

Endpoint tests: dispatch is mocked — no broker, no Whisper, no filesystem writes.
Task tests: called directly with an injected test session and mocked call_whisper_asr.
"""

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlmodel import Session

from app.api.schemas.enums import InputStatus, InputType
from app.db.repositories import get_input, get_job_by_uuid
from app.models import Input, Job
from app.tasks.transcribe import transcribe_audio_task

VOICE_URL = "/api/v1/input/voice"

# Minimal valid WAV bytes (44-byte header + silence) — passes extension check.
_WAV_BYTES = b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"


# ---------------------------------------------------------------------------
# POST /api/v1/input/voice — endpoint tests (dispatch mocked)
# ---------------------------------------------------------------------------

class TestSubmitVoiceInput:

    def _post(self, client, filename="memo.wav", content=None, fields=None, whisper_up=True):
        mock_result = MagicMock()
        mock_result.id = "celery-task-uuid-001"
        # Dispatch is owned by InputService.process_voice_upload — patch there.
        with patch("app.api.routes.input.check_whisper_available", return_value=whisper_up), \
             patch("app.services.input.transcribe_audio_task") as mock_task, \
             patch("pathlib.Path.write_bytes"):
            mock_task.delay.return_value = mock_result
            resp = client.post(
                VOICE_URL,
                files={"audio_file": (filename, io.BytesIO(content or _WAV_BYTES), "audio/wav")},
                data=fields or {},
            )
            return resp, mock_task

    def test_201_returns_required_fields(self, client):
        resp, _ = self._post(client)
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "queued"
        assert body["input_type"] == "voice"
        assert "input_id" in body
        assert "job_id" in body
        assert "poll_url" in body
        assert "estimated_processing_seconds" in body

    def test_201_poll_url_points_to_input_record(self, client):
        resp, _ = self._post(client)
        body = resp.json()
        assert body["poll_url"] == f"/api/v1/input/{body['input_id']}"

    def test_201_creates_queued_input_row(self, client, db):
        resp, _ = self._post(client)
        input_id = resp.json()["input_id"]
        from uuid import UUID
        record = get_input(db, UUID(input_id))
        assert record is not None
        assert record.status == InputStatus.queued
        assert record.input_type == InputType.voice
        assert record.original_filename == "memo.wav"

    def test_201_creates_transcription_job_row(self, client, db):
        resp, _ = self._post(client)
        job_id = resp.json()["job_id"]
        job = get_job_by_uuid(db, job_id)
        assert job is not None
        assert job.job_type == "transcription"
        assert job.status == "queued"
        assert job.celery_task_id == "celery-task-uuid-001"

    def test_201_dispatch_called_with_input_id_and_job_id(self, client, db):
        resp, mock_task = self._post(client)
        body = resp.json()
        mock_task.delay.assert_called_once()
        call_args = mock_task.delay.call_args[0]
        assert call_args[0] == body["input_id"]   # input_id_str
        assert call_args[2] == body["job_id"]      # job_id_str
        # call_args[1] is the audio_path (filesystem path string)
        assert body["input_id"] in call_args[1]

    def test_201_optional_metadata_stored_on_input(self, client, db):
        resp, _ = self._post(client, fields={
            "station_id": "STA-045",
            "responder_badge": "FD-7842",
            "incident_date_hint": "2024-07-10",
        })
        assert resp.status_code == 201
        from uuid import UUID
        record = get_input(db, UUID(resp.json()["input_id"]))
        assert record.station_id == "STA-045"
        assert record.responder_badge == "FD-7842"
        assert str(record.incident_date_hint) == "2024-07-10"

    def test_415_unsupported_format_rejected(self, client):
        resp, _ = self._post(client, filename="memo.pdf")
        assert resp.status_code == 415
        body = resp.json()
        assert body["error_code"] == "UNSUPPORTED_FORMAT"
        assert "accepted_formats" in body["detail"]
        assert "wav" in body["detail"]["accepted_formats"]

    def test_415_no_extension_rejected(self, client):
        resp, _ = self._post(client, filename="audiofile")
        assert resp.status_code == 415
        assert resp.json()["error_code"] == "UNSUPPORTED_FORMAT"

    def test_413_oversize_file_rejected(self, client, monkeypatch):
        monkeypatch.setattr("app.api.routes.input._MAX_AUDIO_BYTES", 5)
        resp, _ = self._post(client, content=b"toolong")  # 7 bytes > 5
        assert resp.status_code == 413
        body = resp.json()
        assert body["error_code"] == "FILE_TOO_LARGE"
        assert body["detail"]["max_size_bytes"] == 5
        assert body["detail"]["received_size_bytes"] == 7

    def test_503_when_whisper_unavailable(self, client):
        resp, _ = self._post(client, whisper_up=False)
        assert resp.status_code == 503
        body = resp.json()
        assert body["error_code"] == "STT_UNAVAILABLE"

    def test_422_missing_audio_file(self, client):
        with patch("app.api.routes.input.check_whisper_available", return_value=True):
            resp = client.post(VOICE_URL, data={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# transcribe_audio_task — unit tests (no broker, direct call, mocked Whisper)
# ---------------------------------------------------------------------------

def _seed_input_and_job(session: Session):
    """Insert a queued Input and Job, return both refreshed."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    inp = Input(
        input_type=InputType.voice,
        status=InputStatus.queued,
        original_filename="test.wav",
        created_at=now,
        updated_at=now,
    )
    session.add(inp)
    job = Job(celery_task_id="celery-test-id", job_type="transcription", status="queued")
    session.add(job)
    session.commit()
    session.refresh(inp)
    session.refresh(job)
    return inp, job


class TestTranscribeAudioTask:

    def _run_task(self, inp, job, test_engine, whisper_side_effect=None, whisper_return="Transcribed text here."):
        """
        Call the task function directly against the in-memory DB.
        Mocks get_session (so the task uses the test engine) and call_whisper_asr.
        Also mocks Path.read_bytes so no filesystem access is needed.
        """
        def _gen():
            with Session(test_engine) as s:
                yield s

        with patch("app.tasks.transcribe.get_session", side_effect=_gen), \
             patch("app.tasks.transcribe.call_whisper_asr") as mock_whisper, \
             patch.object(Path, "read_bytes", return_value=b"fake_audio_bytes"):
            if whisper_side_effect is not None:
                mock_whisper.side_effect = whisper_side_effect
            else:
                mock_whisper.return_value = whisper_return
            try:
                transcribe_audio_task(str(inp.input_id), "/data/audio/test.wav", job.job_id)
            except (ConnectionError, RuntimeError):
                pass  # expected on failure tests

    def test_success_input_becomes_ready_with_transcript(self, db, test_engine):
        inp, job = _seed_input_and_job(db)

        self._run_task(inp, job, test_engine, whisper_return="Incident at Main St, two casualties.")

        db.refresh(inp)
        assert inp.status == InputStatus.ready
        assert inp.transcript == "Incident at Main St, two casualties."
        assert inp.character_count == len("Incident at Main St, two casualties.")
        assert inp.word_count == len(["Incident", "at", "Main", "St,", "two", "casualties."])

    def test_success_job_becomes_completed_with_result_url(self, db, test_engine):
        inp, job = _seed_input_and_job(db)

        self._run_task(inp, job, test_engine, whisper_return="Incident at Main St.")

        db.refresh(job)
        assert job.status == "completed"
        assert job.result_url == f"/api/v1/input/{inp.input_id}"

    def test_connection_error_input_failed_error_detail(self, db, test_engine):
        inp, job = _seed_input_and_job(db)

        self._run_task(inp, job, test_engine, whisper_side_effect=ConnectionError("Cannot reach Whisper"))

        db.refresh(inp)
        assert inp.status == InputStatus.failed
        assert "Cannot reach Whisper" in inp.error_detail

    def test_connection_error_job_failed_with_stt_unavailable_code(self, db, test_engine):
        inp, job = _seed_input_and_job(db)

        self._run_task(inp, job, test_engine, whisper_side_effect=ConnectionError("Cannot reach Whisper"))

        db.refresh(job)
        assert job.status == "failed"
        assert job.error["error_code"] == "STT_UNAVAILABLE"
        assert "Cannot reach Whisper" in job.error["message"]

    def test_runtime_error_input_failed_error_detail(self, db, test_engine):
        inp, job = _seed_input_and_job(db)

        self._run_task(inp, job, test_engine, whisper_side_effect=RuntimeError("HTTP 500 from Whisper"))

        db.refresh(inp)
        assert inp.status == InputStatus.failed
        assert "HTTP 500 from Whisper" in inp.error_detail

    def test_runtime_error_job_failed_with_transcription_failed_code(self, db, test_engine):
        inp, job = _seed_input_and_job(db)

        self._run_task(inp, job, test_engine, whisper_side_effect=RuntimeError("HTTP 500 from Whisper"))

        db.refresh(job)
        assert job.status == "failed"
        assert job.error["error_code"] == "TRANSCRIPTION_FAILED"
        assert "HTTP 500 from Whisper" in job.error["message"]

    def test_success_input_transitions_through_transcribing(self, db, test_engine):
        """The task sets transcribing before calling Whisper and ready after."""
        inp, job = _seed_input_and_job(db)
        observed_statuses: list[str] = []

        original_update = __import__(
            "app.db.repositories", fromlist=["update_input"]
        ).update_input

        def tracking_update(session, input_obj):
            observed_statuses.append(input_obj.status.value)
            return original_update(session, input_obj)

        def _gen():
            with Session(test_engine) as s:
                yield s

        with patch("app.tasks.transcribe.get_session", side_effect=_gen), \
             patch("app.tasks.transcribe.call_whisper_asr", return_value="Hello world text."), \
             patch("app.tasks.transcribe.update_input", side_effect=tracking_update), \
             patch.object(Path, "read_bytes", return_value=b"fake"):
            transcribe_audio_task(str(inp.input_id), "/data/audio/test.wav", job.job_id)

        assert "transcribing" in observed_statuses
        assert "ready" in observed_statuses
        assert observed_statuses.index("transcribing") < observed_statuses.index("ready")
