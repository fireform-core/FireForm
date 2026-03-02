"""
Tests for src/transcriber.py and POST /transcribe/
"""
import pytest
from unittest.mock import MagicMock, patch

from src.transcriber import Transcriber, SUPPORTED_FORMATS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_model(transcript: str = "Hello world", language: str = "en"):
    segment = MagicMock()
    segment.text = transcript

    info = MagicMock()
    info.language = language
    info.language_probability = 0.99
    info.duration = 3.0

    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([segment], info)
    return mock_model


def _make_transcriber(mock_model):
    """Bypass __init__ and inject a mock model directly."""
    t = Transcriber.__new__(Transcriber)
    t._model = mock_model
    return t


# ---------------------------------------------------------------------------
# Unit tests — Transcriber class
# ---------------------------------------------------------------------------

def test_transcribe_returns_string(tmp_path):
    audio_file = tmp_path / "test.wav"
    audio_file.write_bytes(b"fake audio data")

    transcriber = _make_transcriber(_make_mock_model("Officer Voldemort at 456 Oak Street"))
    result = transcriber.transcribe(str(audio_file))

    assert result == "Officer Voldemort at 456 Oak Street"


def test_transcribe_file_not_found():
    transcriber = _make_transcriber(_make_mock_model())

    with pytest.raises(FileNotFoundError):
        transcriber.transcribe("/nonexistent/path/audio.wav")


def test_transcribe_unsupported_format(tmp_path):
    bad_file = tmp_path / "audio.xyz"
    bad_file.write_bytes(b"data")

    transcriber = _make_transcriber(_make_mock_model())

    with pytest.raises(ValueError, match="Unsupported audio format"):
        transcriber.transcribe(str(bad_file))


def test_transcribe_bytes_returns_transcript():
    transcriber = _make_transcriber(_make_mock_model("Test transcript"))
    result = transcriber.transcribe_bytes(b"fake audio bytes", suffix=".wav")

    assert result == "Test transcript"


def test_all_supported_formats_accepted(tmp_path):
    transcriber = _make_transcriber(_make_mock_model("hello"))

    for fmt in SUPPORTED_FORMATS:
        audio_file = tmp_path / f"test{fmt}"
        audio_file.write_bytes(b"fake audio")
        result = transcriber.transcribe(str(audio_file))
        assert isinstance(result, str)


def test_faster_whisper_not_installed():
    with patch.dict("sys.modules", {"faster_whisper": None}):
        with pytest.raises(ImportError, match="faster-whisper is not installed"):
            Transcriber()


# ---------------------------------------------------------------------------
# API route tests — POST /transcribe/
# ---------------------------------------------------------------------------

def test_transcribe_endpoint_success(client):
    mock_transcript = "Officer Voldemort at 456 Oak Street."

    # Transcriber is lazily imported inside the route function body, so we
    # patch it at the source module rather than at the route module namespace.
    with patch("src.transcriber.Transcriber") as MockTranscriber:
        MockTranscriber.return_value.transcribe_bytes.return_value = mock_transcript

        response = client.post(
            "/transcribe/",
            files={"file": ("incident.wav", b"fake audio bytes", "audio/wav")},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["transcript"] == mock_transcript
    assert data["filename"] == "incident.wav"


def test_transcribe_endpoint_unsupported_format(client):
    response = client.post(
        "/transcribe/",
        files={"file": ("incident.pdf", b"not audio", "application/pdf")},
    )
    assert response.status_code == 422


def test_transcribe_endpoint_no_file(client):
    response = client.post("/transcribe/")
    assert response.status_code == 422
