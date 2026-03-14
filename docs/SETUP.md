# FireForm Developer Setup Guide

This guide walks you through setting up FireForm for local development on Windows, macOS, and Linux.

## Prerequisites

| Dependency | Version | Installation |
|-----------|---------|-------------|
| **Python** | 3.11+ | [python.org/downloads](https://www.python.org/downloads/) |
| **Docker** | 20.10+ | [docs.docker.com/get-docker](https://docs.docker.com/get-docker/) |
| **Docker Compose** | 2.0+ | Included with Docker Desktop |
| **Ollama** | Latest | [ollama.com/download](https://ollama.com/download) |
| **Git** | Any | [git-scm.com](https://git-scm.com/) |
| **Make** | Any | See [Installing Make](#installing-make) below |

---

## Option A: Docker Setup (Recommended)

Docker provides a consistent environment across all platforms.

### Step 1 — Clone the Repository

```bash
# Fork the repo on GitHub first, then:
git clone https://github.com/<your-username>/FireForm.git
cd FireForm
```

### Step 2 — Build Containers

```bash
make build
```

This builds the `fireform-app` container (Python 3.11-slim) and pulls the `ollama/ollama:latest` image.

### Step 3 — Start Containers

```bash
make up
```

This starts two containers:
- `fireform-app` — the FastAPI backend (port `8000`)
- `fireform-ollama` — the Ollama LLM server (port `11434`)

### Step 4 — Pull the LLM Model

```bash
make pull-model
```

This downloads the Mistral model (~4 GB) into the Ollama container. This only needs to be done once — the model persists in a Docker volume.

> **Note:** This download can take several minutes depending on your connection. Do not interrupt it.

### Step 5 — Verify

```bash
# Check containers are running
docker compose ps

# Check the API is responding
curl http://localhost:8000/docs
```

Open [http://localhost:8000/docs](http://localhost:8000/docs) in your browser. You should see the Swagger UI.

### Useful Docker Commands

| Command | Description |
|---------|-------------|
| `make fireform` | Build, start, and open a shell (all-in-one) |
| `make shell` | Open a bash shell inside the app container |
| `make exec` | Run `src/main.py` inside the container |
| `make logs` | View live logs from all containers |
| `make logs-app` | View logs from the app container only |
| `make logs-ollama` | View logs from the Ollama container only |
| `make down` | Stop all containers |
| `make clean` | Stop and remove all containers + volumes |
| `make help` | Show all available commands |

---

## Option B: Local Setup (Without Docker)

Use this if you prefer running everything natively.

### Step 1 — Clone and Create Virtual Environment

```bash
git clone https://github.com/<your-username>/FireForm.git
cd FireForm
python -m venv venv
```

Activate the virtual environment:

```bash
# Linux / macOS
source venv/bin/activate

# Windows (PowerShell)
venv\Scripts\Activate.ps1

# Windows (CMD)
venv\Scripts\activate.bat
```

### Step 2 — Install Dependencies

```bash
pip install -r requirements.txt
```

> **Note:** On some systems you may also need to install `python-multipart` and `pypdf` manually if they are not yet listed in `requirements.txt`:
> ```bash
> pip install python-multipart pypdf
> ```

### Step 3 — Install Ollama and Pull Mistral

1. Download and install Ollama from [ollama.com/download](https://ollama.com/download)
2. Start Ollama:
   ```bash
   ollama serve
   ```
3. In a **new terminal**, pull the Mistral model:
   ```bash
   ollama pull mistral
   ```

### Step 4 — Initialize the Database

```bash
python -m api.db.init_db
```

You should see a `fireform.db` file created in the project root.

### Step 5 — Start the API Server

```bash
uvicorn api.main:app --reload
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
```

### Step 6 — Verify

Open [http://localhost:8000/docs](http://localhost:8000/docs) in your browser to see the Swagger UI.

---

## Running Tests

```bash
# Run all tests (local)
python -m pytest tests/ -v

# Run all tests (Docker)
docker compose exec app python3 -m pytest tests/ -v

# Run a specific test file
python -m pytest tests/test_templates.py -v

# Run with coverage (if pytest-cov is installed)
python -m pytest tests/ --cov=api --cov=src -v
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API endpoint. Set to `http://ollama:11434` in Docker. |
| `PYTHONPATH` | — | Set to `/app/src` in Docker. For local dev, run from project root. |
| `PYTHONUNBUFFERED` | — | Set to `1` in Docker for real-time log output. |

---

## Common Issues and Fixes

### `ImportError: libGL.so.1: cannot open shared object file`

**Cause:** OpenCV requires system-level graphics libraries not included in `python:3.11-slim`.

**Fix (Docker):** Ensure your `Dockerfile` includes:
```dockerfile
RUN apt-get update && apt-get install -y \
    curl \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
```

**Fix (Linux local):**
```bash
sudo apt-get install libgl1 libglib2.0-0
```

---

### `NameError: name 'Union' is not defined`

**Cause:** `src/main.py` uses `Union` in a type hint but doesn't import it.

**Fix:** Add to the top of `src/main.py`:
```python
from typing import Union
```

> This is a known issue tracked in [Issue #187](https://github.com/fireform-core/FireForm/issues/187).

---

### `Form data requires "python-multipart" to be installed`

**Cause:** `python-multipart` is required by FastAPI for file uploads but is not listed in `requirements.txt`.

**Fix:**
```bash
pip install python-multipart
```

> This is a known issue tracked in [Issue #204](https://github.com/fireform-core/FireForm/issues/204).

---

### Port `11434` already in use

**Cause:** Another instance of Ollama is already running on your system.

**Fix:**
```bash
# Linux / macOS
sudo lsof -i :11434

# Windows (PowerShell)
netstat -aon | findstr :11434

# Kill the process or stop the existing Ollama instance
```

---

### Port `8000` not accessible from host

**Cause:** The Docker Compose file may be missing the port mapping.

**Fix:** Ensure `docker-compose.yml` has the following under the `app` service:
```yaml
ports:
  - "8000:8000"
```

> This is a known issue tracked in [Issue #224](https://github.com/fireform-core/FireForm/issues/224).

---

### `ModuleNotFoundError: No module named 'pypdf'`

**Cause:** `pypdf` is used in template routes but may not be in `requirements.txt`.

**Fix:**
```bash
pip install pypdf
```

---

## Resetting the Database

If your database gets into a bad state:

```bash
# Delete the existing database
rm fireform.db

# Recreate it
python -m api.db.init_db
```

---

## Architecture Overview

FireForm follows this pipeline:

```
Voice Memo / Text Input
        │
        ▼
┌─────────────────┐
│   FastAPI (API)  │  POST /forms/fill
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Controller     │  Orchestrates the flow
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  FileManipulator │  Coordinates LLM + PDF
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌───────┐ ┌───────┐
│  LLM  │ │Filler │
│(Ollama│ │(pdfrw)│
│Mistral│ │       │
└───┬───┘ └───┬───┘
    │         │
    ▼         ▼
 JSON      Filled PDF
```

For more details, see the docstrings in `src/controller.py`, `src/file_manipulator.py`, `src/llm.py`, and `src/filler.py`.
