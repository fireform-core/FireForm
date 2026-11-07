"""Central configuration.

Single source of truth for paths, the database URL, external service hosts and
CORS. Read environment once here so the rest of the app imports settings instead
of calling os.getenv() in scattered places.
"""

import os
import sys
from pathlib import Path

# Repo root or PyInstaller bundle root.
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    BASE_DIR = Path(sys._MEIPASS).resolve()
else:
    BASE_DIR = Path(__file__).resolve().parents[2]

# --- App metadata ---------------------------------------------------------
APP_TITLE = "FireForm API"
APP_VERSION = "1.1.0"

# --- Desktop Mode ---------------------------------------------------------
FIREFORM_DESKTOP = os.getenv("FIREFORM_DESKTOP", "false").lower() in ("true", "1", "yes")

# --- Runtime data paths ---------------------------------------------------
# Uploaded templates and generated PDFs. Project-relative paths the API echoes
# back to the client are resolved against BASE_DIR (the "inside the project"
# guard in the templates routes). Override the data dir with FIREFORM_DATA_DIR.
DATA_DIR = Path(os.getenv("FIREFORM_DATA_DIR", BASE_DIR / "data")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Directory new uploads land in, as a project-relative string (was "src/inputs"
# before the restructure). Override with FIREFORM_TEMPLATE_DIR.
DEFAULT_TEMPLATE_DIR = os.getenv("FIREFORM_TEMPLATE_DIR", "data/inputs")
# Bundled PDF behind the seeded "Manual Test Template"; never deleted with a template.
SEED_TEMPLATE_PDF_PATH = "data/inputs/file_template_manual.pdf"

# --- Database -------------------------------------------------------------
_DEFAULT_DATABASE_URL = (
    f"sqlite:///{DATA_DIR / 'fireform.db'}"
    if FIREFORM_DESKTOP
    else "postgresql+psycopg2://fireform:fireform@localhost:5432/fireform"
)
DATABASE_URL = os.getenv("DATABASE_URL", _DEFAULT_DATABASE_URL)
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
DB_ECHO = os.getenv("FIREFORM_DB_ECHO", "false" if FIREFORM_DESKTOP else "true").lower() == "true"

# --- External services ----------------------------------------------------
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "300"))
OLLAMA_PULL_TIMEOUT = int(os.getenv("OLLAMA_PULL_TIMEOUT", "120"))
OLLAMA_INSTALLABLE_MODELS = os.getenv("OLLAMA_INSTALLABLE_MODELS", "").strip()

# --- LLM providers --------------------------------------------------------
# Every provider with a non empty <PROVIDER>_MODELS is enabled, so several can
# run side by side and each request picks one. LLM_PROVIDER and LLM_MODEL pick
# the default. Kept as raw strings, app/services/llm/settings.py parses and
# validates them at startup. Documented in docker/.env.example.
LLM_PROVIDER = (os.getenv("LLM_PROVIDER", "").strip() or "ollama").lower()
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()
LLM_TIMEOUT = os.getenv("LLM_TIMEOUT", str(OLLAMA_TIMEOUT)).strip()
LLM_MAX_RETRIES = os.getenv("LLM_MAX_RETRIES", "3").strip()
LLM_ALLOW_EXTERNAL = os.getenv("LLM_ALLOW_EXTERNAL", "false").strip()
LLM_TEMPERATURE = os.getenv("LLM_TEMPERATURE", "0").strip()


def _provider_env(prefix: str, **defaults: str) -> dict[str, str]:
    """The <PREFIX>_* settings of one provider, keyed without the prefix."""
    keys = ("BASE_URL", "API_KEY", "MODELS", "MAX_TOKENS", "STRUCTURED_OUTPUT")
    return {key: os.getenv(f"{prefix}_{key}", defaults.get(key, "")).strip() for key in keys}


# Keyed by LLMProvider value. Ollama keeps its own OLLAMA_HOST and lists every
# pulled model unless OLLAMA_MODELS says otherwise.
LLM_PROVIDER_ENV = {
    "ollama": {**_provider_env("OLLAMA", MODELS="*"), "BASE_URL": OLLAMA_HOST},
    "openai": _provider_env("OPENAI"),
    "gemini": _provider_env("GEMINI"),
    "anthropic": _provider_env("ANTHROPIC"),
    "custom": _provider_env("CUSTOM"),
}

WHISPER_HOST = os.getenv("WHISPER_HOST", "http://localhost:9000").rstrip("/")
WHISPER_ENABLED = os.getenv("WHISPER_ENABLED", "false" if FIREFORM_DESKTOP else "true").lower() in ("true", "1", "yes")

# --- Celery / Redis -------------------------------------------------------
_DEFAULT_CELERY_BROKER = "" if FIREFORM_DESKTOP else "redis://localhost:6379/0"
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", _DEFAULT_CELERY_BROKER)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", _DEFAULT_CELERY_BROKER)

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
LLM_SECRET_KEY = os.getenv("LLM_SECRET_KEY", "").strip()
_DEFAULT_LLM_SECRET_KEY_FILE = (
    Path("/data/secrets/llm_secret.key")
    if Path("/data/secrets").is_dir()
    else BASE_DIR / "data" / "secrets" / "llm_secret.key"
)
LLM_SECRET_KEY_FILE = Path(os.getenv("LLM_SECRET_KEY_FILE", str(_DEFAULT_LLM_SECRET_KEY_FILE))).expanduser()

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