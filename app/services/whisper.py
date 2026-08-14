import requests

from app.core.config import WHISPER_HOST


def call_whisper_asr(audio_bytes: bytes, filename: str, content_type: str) -> str:
    """Post audio to the local Whisper ASR sidecar and return the transcript.

    Raises ConnectionError if the service is unreachable, RuntimeError for any
    other HTTP failure. Callers map these to their own error codes.
    """
    whisper_url = f"{WHISPER_HOST}/asr"
    files = {"audio_file": (filename, audio_bytes, content_type)}
    params = {"task": "transcribe", "output": "json", "encode": "true"}

    try:
        response = requests.post(whisper_url, params=params, files=files, timeout=120)
        response.raise_for_status()
    except requests.exceptions.ConnectionError as exc:
        raise ConnectionError(
            f"Could not connect to the speech-to-text service at {whisper_url}. "
            "Please ensure the whisper service is running."
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Transcription failed: {exc}") from exc

    try:
        return (response.json().get("text") or "").strip()
    except ValueError:
        return response.text.strip()


def check_whisper_available() -> bool:
    """Return True if the Whisper sidecar responds with a successful status."""
    try:
        return requests.get(WHISPER_HOST, timeout=3).ok
    except requests.exceptions.RequestException:
        return False
