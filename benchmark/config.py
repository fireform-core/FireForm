"""Benchmark settings.

Every value can be set as an environment variable. benchmark/.env is read
first if it exists; it is gitignored, so put your own Ollama server there:

    cp benchmark/.env.example benchmark/.env

Variables already set in the shell win over the .env file.

The model under test is configured by app.core.config (OLLAMA_HOST,
OLLAMA_MODEL, OLLAMA_TIMEOUT), which reads the environment when it is first
imported, so import this module before anything from `app`.
"""

import os

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(HERE, ".env")


def load_env_file(path):
    """KEY=value lines into os.environ, without overriding what is already set."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


load_env_file(ENV_FILE)

# --- LLM judge -----------------------------------------------------------
# Defaults to the same Ollama server as the model under test.
JUDGE_HOST = os.getenv("JUDGE_HOST", os.getenv("OLLAMA_HOST", "http://localhost:11434")).rstrip("/")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "qwen3.5:4b")
JUDGE_TIMEOUT_SECONDS = float(os.getenv("JUDGE_TIMEOUT_SECONDS", "300"))
JUDGE_CONTEXT_TOKENS = int(os.getenv("JUDGE_CONTEXT_TOKENS", "32768"))
