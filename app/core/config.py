"""Central configuration.

Single source of truth for paths, the database URL, external service hosts and
CORS. Read environment once here so the rest of the app imports settings instead
of calling os.getenv() in scattered places.
"""

import os
from pathlib import Path

# Repo root. config.py lives at app/core/config.py -> parents[2] is the repo root.
BASE_DIR = Path(__file__).resolve().parents[2]

# --- App metadata ---------------------------------------------------------
APP_TITLE = "FireForm API"
APP_VERSION = "1.1.0"

# --- Runtime data paths ---------------------------------------------------
# Uploaded templates and generated PDFs. Project-relative paths the API echoes
# back to the client are resolved against BASE_DIR (the "inside the project"
# guard in the templates routes). Override the data dir with FIREFORM_DATA_DIR.
DATA_DIR = Path(os.getenv("FIREFORM_DATA_DIR", BASE_DIR / "data")).resolve()

# Directory new uploads land in, as a project-relative string (was "src/inputs"
# before the restructure). Override with FIREFORM_TEMPLATE_DIR.
DEFAULT_TEMPLATE_DIR = os.getenv("FIREFORM_TEMPLATE_DIR", "data/inputs")

# --- Database -------------------------------------------------------------
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://fireform:fireform@localhost:5432/fireform",
)
DB_ECHO = os.getenv("FIREFORM_DB_ECHO", "true").lower() == "true"

# --- External services ----------------------------------------------------
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")
WHISPER_HOST = os.getenv("WHISPER_HOST", "http://localhost:9000").rstrip("/")

# --- Celery / Redis -------------------------------------------------------
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

# --- CORS -----------------------------------------------------------------
_DEFAULT_ORIGINS = "http://127.0.0.1:5173,http://localhost:5173"
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("FRONTEND_ORIGINS", _DEFAULT_ORIGINS).split(",")
    if origin.strip()
]

# --- Error handling -------------------------------------------------------
# Advisory Retry-After sent to clients on 503 responses. This is a client
# hint, not a measured backpressure value — the app has no queue-depth signal.
RETRY_AFTER_SECONDS = 30

# Polling hint returned by GET /input/{id} when a voice input is still queued
# or transcribing. Value matches the contract example (contracts/path/input.yaml).
INPUT_POLL_INTERVAL_SECONDS = 5

# --- API Versioning -------------------------------------------------------
API_PREFIX = "/api/v1"

# --- Security & Access Control ---------------------------------------------
FIREFORM_API_KEY = os.getenv("FIREFORM_API_KEY", "")

# --- Data Retention --------------------------------------------------------
RETENTION_PERIOD_DAYS = int(os.getenv("RETENTION_PERIOD_DAYS", "30"))

# --- Audio storage --------------------------------------------------------
# Voice input audio files land here: {AUDIO_DIR}/{input_id}.{ext}
AUDIO_DIR = DATA_DIR / "audio"

# Advisory estimate returned in VoiceInputResponse.estimated_processing_seconds.
ESTIMATED_TRANSCRIPTION_SECONDS = int(os.getenv("ESTIMATED_TRANSCRIPTION_SECONDS", "30"))

# Canonical audio format mapping — single source of truth for both the route
# (membership check, 415 detail list) and the task (content-type lookup).
# Dict insertion order gives the stable list shown in error responses.
AUDIO_CONTENT_TYPES: dict[str, str] = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "m4a": "audio/m4a",
    "ogg": "audio/ogg",
    "webm": "audio/webm",
}
ALLOWED_AUDIO_EXTENSIONS: frozenset[str] = frozenset(AUDIO_CONTENT_TYPES)