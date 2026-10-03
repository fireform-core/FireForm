"""run_info.json: everything needed to understand and recreate a run.

Written into every run folder; --baseline publishes it with the results.
Server addresses are deliberately left out (they may be private); models are
identified by name and digest instead, which pins the exact weights.
"""

import hashlib
import os
import platform
import subprocess
import time
from importlib import metadata

import requests

import llm_judge
from app.core.config import OLLAMA_HOST, OLLAMA_TIMEOUT
from app.services.form_filler import filler

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGES = ["pypdf", "pdfplumber", "requests"]


def collect(model, docs, argv):
    """Settings known before the run starts."""
    return {
        "date": time.strftime("%Y-%m-%d %H:%M:%S %z"),
        "command": "python3 run.py " + " ".join(argv),
        "code": git_state(),
        "model_under_test": {
            "model": model,
            **ollama_model_info(OLLAMA_HOST, model),
            "options": filler.OPTIONS,
            "timeout_seconds": OLLAMA_TIMEOUT,
            "prompt_file": "prompt.txt",
            "prompt_sha256": sha256(filler.PROMPT),
        },
        "judge": {
            "model": llm_judge.JUDGE_MODEL,
            **ollama_model_info(llm_judge.JUDGE_HOST, llm_judge.JUDGE_MODEL),
            "options": llm_judge.JUDGE_OPTIONS,
            "timeout_seconds": llm_judge.JUDGE_TIMEOUT_SECONDS,
            "threshold": llm_judge.JUDGE_THRESHOLD,
        },
        "ollama_version": ollama_version(OLLAMA_HOST),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            **{name: package_version(name) for name in PACKAGES},
        },
        "documents": docs,
    }


def add_results(info, scored, skipped, seconds):
    """Averages and skips, known after the run."""
    n = len(scored)
    info["results"] = {
        "documents_scored": n,
        "documents_skipped": {doc: reason for doc, reason in skipped},
        "average_accuracy": round(sum(r["accuracy"] for _, r, _ in scored) / n * 100, 2) if n else None,
        "average_populated_accuracy": (
            round(sum(r["populated_accuracy"] for _, r, _ in scored) / n * 100, 2) if n else None
        ),
        "average_raw_accuracy": round(sum(r["raw_accuracy"] for _, r, _ in scored) / n * 100, 2) if n else None,
        "total_seconds": round(seconds),
    }
    return info


def git_state():
    def git(*args):
        try:
            return subprocess.run(
                ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
            ).stdout.rstrip()
        except (OSError, subprocess.CalledProcessError):
            return None

    changed = git("status", "--porcelain", "--", "app", "benchmark", "requirements.txt")
    return {
        "commit": git("rev-parse", "HEAD"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        # Results are only reproducible from the commit if this is empty
        "uncommitted_changes": [line[3:] for line in changed.splitlines()] if changed else [],
    }


def ollama_model_info(host, model):
    """Digest, size and quantization of the model on its Ollama server."""
    info = {"digest": None, "details": None}
    try:
        tags = requests.get(host + "/api/tags", timeout=10).json()
        for m in tags.get("models", []):
            if m.get("name") == model or m.get("model") == model:
                info["digest"] = m.get("digest")
        show = requests.post(host + "/api/show", json={"model": model}, timeout=10).json()
        info["details"] = show.get("details")
    except (requests.RequestException, ValueError):
        pass
    return info


def ollama_version(host):
    try:
        return requests.get(host + "/api/version", timeout=10).json().get("version")
    except (requests.RequestException, ValueError):
        return None


def package_version(name):
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
