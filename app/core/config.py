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
# Seconds to wait on a single Ollama generate call. One chunk prompt on a small
# local model is slow, so this is generous by design.
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "600"))
# Ceiling on tokens generated per chunk answer. It stops a small model from
# echoing the whole field skeleton back and spending the timeout on it.
#
# Keep these two in step. A section that runs past OLLAMA_TIMEOUT is lost
# outright, while one that hits this ceiling still keeps every field it
# completed before the cut, so the ceiling should be reachable well inside the
# timeout on the slowest model you run. A small model on CPU manages roughly
# three tokens a second, which is where these defaults come from.
OLLAMA_MAX_TOKENS = int(os.getenv("OLLAMA_MAX_TOKENS", "1200"))
WHISPER_HOST = os.getenv("WHISPER_HOST", "http://localhost:9000").rstrip("/")

# --- LLM provider ---------------------------------------------------------
# Which backend answers prompts, one per deployment. "custom" points at any
# endpoint speaking the OpenAI chat completions API and needs LLM_BASE_URL.
# The OLLAMA_* settings above stay the Ollama provider's defaults, so an
# existing .env keeps working untouched. Meanings are documented in
# docker/.env.example.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "").strip().rstrip("/")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()

LLM_EXTRA_HEADERS = os.getenv("LLM_EXTRA_HEADERS", "").strip()
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", str(OLLAMA_TIMEOUT)))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", str(OLLAMA_MAX_TOKENS)))

# Hosted providers mean incident narratives leave the department's hardware,
# which is the one thing FireForm promises will not happen. They refuse to
# start until this is switched on deliberately.
LLM_ALLOW_EXTERNAL = os.getenv("LLM_ALLOW_EXTERNAL", "false").strip().lower() == "true"

# A 429 is the provider asking us to wait, so it is worth waiting out. Anything
# still limited after all of these tries is a quota problem no retry fixes.
LLM_RATE_LIMIT_RETRIES = int(os.getenv("LLM_RATE_LIMIT_RETRIES", "10"))
LLM_RATE_LIMIT_WAIT_SECONDS = float(os.getenv("LLM_RATE_LIMIT_WAIT_SECONDS", "10"))
LLM_RATE_LIMIT_MAX_WAIT_SECONDS = float(os.getenv("LLM_RATE_LIMIT_MAX_WAIT_SECONDS", "60"))
LLM_RESPECT_RETRY_AFTER = os.getenv("LLM_RESPECT_RETRY_AFTER", "true").strip().lower() == "true"
LLM_SERVER_RETRIES = int(os.getenv("LLM_SERVER_RETRIES", "2"))
LLM_SERVER_RETRY_WAIT_SECONDS = float(os.getenv("LLM_SERVER_RETRY_WAIT_SECONDS", "2"))

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

# Polling hint returned by GET /extract/{id} while an extraction is still
# processing. Matches the contract example (contracts/path/extraction.yaml).
EXTRACTION_POLL_INTERVAL_SECONDS = 5

# Advisory estimate returned in the 202 body of POST /extract/{input_id}.
ESTIMATED_EXTRACTION_SECONDS = int(os.getenv("ESTIMATED_EXTRACTION_SECONDS", "60"))

# --- Extraction worker ----------------------------------------------------
# How many chunk prompts run at once. A local server queues whatever it cannot
# serve concurrently, so going wider than it buys nothing but memory pressure.
# A hosted provider will rate limit instead, which the retry policy absorbs.
EXTRACTION_MAX_PARALLEL = int(
    os.getenv("LLM_MAX_PARALLEL", os.getenv("OLLAMA_NUM_PARALLEL", "4"))
)

# Extra attempts after a chunk's first result fails validation. One retry, with
# the rejected value named in the prompt; a chunk that misses twice is left for
# manual entry rather than guessed at.
EXTRACTION_CHUNK_RETRIES = int(os.getenv("EXTRACTION_CHUNK_RETRIES", "1"))

# One input gets one extraction, which makes re-testing the same narrative mean
# re-uploading it. Switching this on lets a repeat run through; every run still
# gets its own extraction and its own draft incident, so the old ones stay put.
# Development only, leave it off anywhere real.
EXTRACTION_ALLOW_RERUN = os.getenv("EXTRACTION_ALLOW_RERUN", "false").strip().lower() == "true"

# The contract file the chunk registry reads its tiers and triggers from.
INCIDENT_CONTRACT_PATH = Path(
    os.getenv("INCIDENT_CONTRACT_PATH", BASE_DIR / "contracts" / "schemas" / "incident-contract.yaml")
)

# Deployment context the extractor falls back on when the narrative is silent:
# timezone for resolving relative dates, country, currency for Money amounts.
# A request can override any of them through ExtractionRequest.defaults.
DEFAULT_COUNTRY = os.getenv("FIREFORM_DEFAULT_COUNTRY", "US")
DEFAULT_TIMEZONE = os.getenv("FIREFORM_DEFAULT_TIMEZONE", "UTC")
DEFAULT_CURRENCY = os.getenv("FIREFORM_DEFAULT_CURRENCY", "USD")

# --- API Versioning -------------------------------------------------------
API_PREFIX = "/api/v1"

# --- Security & Access Control ---------------------------------------------
FIREFORM_API_KEY = os.getenv("FIREFORM_API_KEY", "")

# --- Data Retention --------------------------------------------------------
RETENTION_PERIOD_DAYS = int(os.getenv("RETENTION_PERIOD_DAYS", "30"))

# --- Template PDF storage and field detection -----------------------------
# Blank agency PDFs uploaded for template authoring land here as
# {TEMPLATE_UPLOAD_DIR}/{upload_id}.pdf. The reference handed back to clients
# is that path taken relative to DATA_DIR, so the two can never drift apart.
TEMPLATE_UPLOAD_DIR = DATA_DIR / "templates" / "uploads"

MAX_TEMPLATE_PDF_BYTES = 50 * 1024 * 1024

# Polling hint returned by the draft endpoints while detection is running.
TEMPLATE_DETECTION_POLL_INTERVAL_SECONDS = 5

# Two thresholds govern the mapping suggester. Below the floor nothing is
# offered at all: an empty list next to a good search box beats a wrong guess,
# because a pre-filled mapping is trusted far more than it deserves. At or above
# the auto-apply mark the top hit is written straight into the field as a
# schema mapping; between the two the suggestions are listed and the user picks.
MAPPING_SUGGESTION_FLOOR = float(os.getenv("MAPPING_SUGGESTION_FLOOR", "0.5"))
MAPPING_AUTO_APPLY_SCORE = float(os.getenv("MAPPING_AUTO_APPLY_SCORE", "0.85"))
MAX_MAPPING_SUGGESTIONS = 5

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

# --- Generated form storage -------------------------------------------------
# Filled form PDFs land here: {FORMS_OUTPUT_DIR}/{form_id}.pdf. Form.pdf_path
# stores this DATA_DIR-relative, same convention as FormTemplate.pdf_template_ref.
FORMS_OUTPUT_DIR = DATA_DIR / "forms" / "generated"

# Advisory estimate returned in the 202 body of POST /forms/generate. Filling
# is pure lookup-and-draw (no LLM), so this is far below the extraction estimate.
ESTIMATED_FORM_GENERATION_SECONDS = int(os.getenv("ESTIMATED_FORM_GENERATION_SECONDS", "10"))

# Polling hint returned by GET /forms/{id}/pdf while generation is still in
# progress. Matches the contract example (contracts/path/forms.yaml).
FORM_GENERATION_POLL_INTERVAL_SECONDS = 5