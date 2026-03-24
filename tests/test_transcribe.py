"""
Tests for Phase 3: Voice Transcription Layer.

All tests mock Whisper model loading so no model download is required.
The mock patches Transcriber._load_model at the class level, which means
any instance (including the route's singleton) will use the fake model.
"""

import io
from unittest.mock import MagicMock, patch

import pytest

from src.transcriber import SUPPORTED_FORMATS, Transcriber

FAKE_TRANSCRIPT = "Engine 12 responding to a structure fire at 1234 Oak Street."


# ---------------------------------------------------------------------------
# Unit tests — Transcriber class
# ---------------------------------------------------------------------------


def _make_mock_model(text: str = FAKE_TRANSCRIPT):
    mock = MagicMock()
    mock.transcribe.return_value = {"text": f"  {text}  "}
    return mock


def test_transcriber_default_model_size():
    t = Transcriber()
    assert t.model_size == "base"


def test_transcriber_custom_model_size():
    t = Transcriber(model_size="small")
    assert t.model_size == "small"


def test_transcriber_invalid_model_size():
    with pytest.raises(ValueError, match="Invalid model size"):
        Transcriber(model_size="giant")


def test_transcribe_strips_whitespace(tmp_path):
    audio = tmp_path / "incident.wav"
    audio.write_bytes(b"fake audio bytes")

    with patch.object(Transcriber, "_load_model", return_value=_make_mock_model()):
        t = Transcriber()
        result = t.transcribe(audio)

    assert result == FAKE_TRANSCRIPT  # leading/trailing whitespace stripped


def test_transcribe_file_not_found():
    t = Transcriber()
    with pytest.raises(FileNotFoundError):
        t.transcribe("nonexistent_audio.wav")


def test_transcribe_unsupported_format(tmp_path):
    bad_file = tmp_path / "report.txt"
    bad_file.write_bytes(b"not audio")

    t = Transcriber()
    with pytest.raises(ValueError, match="Unsupported audio format"):
        t.transcribe(bad_file)


def test_transcribe_bytes_cleans_up_temp_file():
    audio_bytes = b"fake audio bytes"

    created_paths = []

    original_transcribe = Transcriber.transcribe

    def capturing_transcribe(self, path):
        created_paths.append(str(path))
        return FAKE_TRANSCRIPT

    with patch.object(Transcriber, "_load_model", return_value=_make_mock_model()):
        with patch.object(Transcriber, "transcribe", capturing_transcribe):
            t = Transcriber()
            result = t.transcribe_bytes(audio_bytes, suffix=".wav")

    assert result == FAKE_TRANSCRIPT
    # Temp file must have been deleted
    import os
    for p in created_paths:
        assert not os.path.exists(p), f"Temp file was not cleaned up: {p}"


def test_supported_formats_coverage():
    expected = {".wav", ".mp3", ".m4a", ".mp4", ".ogg", ".flac"}
    assert expected == SUPPORTED_FORMATS


# ---------------------------------------------------------------------------
# Endpoint tests — POST /transcribe
# ---------------------------------------------------------------------------


def test_transcribe_endpoint_success(client):
    with patch("api.routes.transcribe._get_transcriber") as mock_getter:
        mock_transcriber = MagicMock()
        mock_transcriber.transcribe_bytes.return_value = FAKE_TRANSCRIPT
        mock_transcriber.model_size = "base"
        mock_getter.return_value = mock_transcriber

        response = client.post(
            "/transcribe",
            files={"file": ("incident.wav", io.BytesIO(b"fake audio"), "audio/wav")},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["text"] == FAKE_TRANSCRIPT
    assert data["audio_filename"] == "incident.wav"
    assert data["model_used"] == "base"


def test_transcribe_endpoint_unsupported_format(client):
    response = client.post(
        "/transcribe",
        files={"file": ("report.txt", io.BytesIO(b"text"), "text/plain")},
    )
    assert response.status_code == 415
    assert "Unsupported audio format" in response.json()["detail"]


def test_transcribe_endpoint_transcriber_error(client):
    with patch("api.routes.transcribe._get_transcriber") as mock_getter:
        mock_transcriber = MagicMock()
        mock_transcriber.transcribe_bytes.side_effect = RuntimeError("Whisper failed")
        mock_getter.return_value = mock_transcriber

        response = client.post(
            "/transcribe",
            files={"file": ("incident.mp3", io.BytesIO(b"audio"), "audio/mpeg")},
        )

    assert response.status_code == 500
    assert "Whisper failed" in response.json()["detail"]


@pytest.mark.parametrize("fmt", [".wav", ".mp3", ".m4a", ".mp4", ".ogg", ".flac"])
def test_transcribe_endpoint_accepts_all_supported_formats(client, fmt):
    with patch("api.routes.transcribe._get_transcriber") as mock_getter:
        mock_transcriber = MagicMock()
        mock_transcriber.transcribe_bytes.return_value = FAKE_TRANSCRIPT
        mock_transcriber.model_size = "base"
        mock_getter.return_value = mock_transcriber

        response = client.post(
            "/transcribe",
            files={"file": (f"audio{fmt}", io.BytesIO(b"audio"), "audio/octet-stream")},
        )

    assert response.status_code == 200
