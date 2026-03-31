# FireForm — Deployment Guide

This guide covers deploying FireForm using Docker. By the end, you will have the full
FireForm stack (FastAPI server + Ollama AI engine) running on any machine with a single command.

---

## Prerequisites

| Requirement | Version | Install |
|------------|---------|---------|
| Docker Desktop | 26.x or newer | [docker.com/get-started](https://www.docker.com/get-started/) |
| WSL2 (Windows only) | latest | `wsl --update` in PowerShell as Admin |
| Git | any | [git-scm.com](https://git-scm.com/) |
| Disk space | ~6GB free | For Docker image + Mistral model (~4GB) |
| RAM | 8GB minimum | 16GB recommended for smooth LLM inference |

---

## Quick Start (Recommended)

```bash
# 1. Clone the repository
git clone https://github.com/fireform-core/FireForm
cd FireForm

# 2. Build and start everything
docker compose build
docker compose up -d

# 3. Pull the AI model (one-time, ~4GB download)
docker compose exec ollama ollama pull mistral

# 4. Open FireForm
#    API + Swagger docs:  http://localhost:8000/docs
#    Web interface:       http://localhost:8000
#    Mobile PWA:          http://localhost:8000/mobile
```

---

## What Runs Inside Docker

| Container | Purpose | Port |
|-----------|---------|------|
| `fireform-app` | FastAPI server — handles all API routes, PDF filling, Data Lake | `8000` |
| `fireform-ollama` | Ollama AI engine — serves Mistral for LLM extraction and semantic mapping | `11434` |

The two containers communicate internally over `fireform-network`. You only interact with port `8000`.

---

## Make Commands Reference

```bash
make fireform       # Build + start + pull Mistral model (full setup)
make build          # Build Docker images only
make up             # Start all containers (background)
make down           # Stop all containers
make logs           # View live logs from all containers
make logs-app       # View live logs from FastAPI app only
make logs-ollama    # View live logs from Ollama only
make shell          # Open bash shell inside the app container
make run            # Start the FastAPI server inside the running container
make pull-model     # Pull the Mistral model into Ollama
make test           # Run the full test suite inside the container
make clean          # Stop containers and remove volumes
make super-clean    # [CAUTION] Remove all containers, networks, and build cache
make help           # Show all commands with descriptions
```

---

## Environment Variables

Set these in `docker-compose.yml` under `app > environment`, or pass via `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_HOST` | `http://ollama:11434` | URL of the Ollama service (internal Docker network) |
| `OLLAMA_TIMEOUT` | `300` | Seconds to wait for LLM response before timeout |
| `FIREFORM_MODEL` | `mistral` | LLM model to use (e.g. `mistral`, `llama3`, `llava`) |
| `PYTHONUNBUFFERED` | `1` | Ensures real-time log output |
| `PYTHONPATH` | `/app` | Project root — required for all `api.*` and `src.*` imports |

### Using a Different Model

```bash
# In docker-compose.yml, change:
- FIREFORM_MODEL=mistral
# To any Ollama-supported model:
- FIREFORM_MODEL=llama3

# Then pull the new model:
docker compose exec ollama ollama pull llama3
```

---

## Verifying the Deployment

### 1. Check containers are running
```bash
docker ps
```
Expected output:
```
CONTAINER ID   IMAGE                  PORTS                     NAMES
xxxxxxxxxxxx   fireform-app           0.0.0.0:8000->8000/tcp    fireform-app
xxxxxxxxxxxx   ollama/ollama:latest   0.0.0.0:11434->11434/tcp  fireform-ollama
```

### 2. Check app started correctly
```bash
docker compose logs app
```
Look for:
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### 3. Test the API
```bash
curl http://localhost:8000/
```
Or open **http://localhost:8000/docs** in your browser — Swagger UI should load.

### 4. Run the test suite
```bash
make test
```
All 83+ tests should pass.

---

## Troubleshooting

### Container exits immediately / `Application startup complete` never appears
```bash
docker compose logs app
```
Read the error. Common causes:

| Error message | Cause | Fix |
|---------------|-------|-----|
| `ModuleNotFoundError: No module named 'X'` | Missing package in `requirements.txt` | Add the package and rebuild |
| `RuntimeError: Form data requires python-multipart` | `python-multipart` missing | Already fixed in this PR |
| `cannot import name 'X' from 'api.routes'` | Wrong `PYTHONPATH` | Ensure `PYTHONPATH=/app` in `docker-compose.yml` |

### Port 8000 already in use
```bash
# Find what's using port 8000
netstat -ano | findstr :8000    # Windows
lsof -i :8000                   # Mac/Linux

# Or change the port in docker-compose.yml:
ports:
  - "8080:8000"   # Use localhost:8080 instead
```

### Ollama container unhealthy / never starts
The `ollama/ollama` image does not include system utilities like `curl` or `wget`.
Do not add a `healthcheck` that depends on these. The app uses `OLLAMA_TIMEOUT=300`
to wait for Ollama to be ready at the application level.

### LLM calls fail / timeout
```bash
# Verify Mistral is pulled
docker compose exec ollama ollama list
# Should show: mistral:latest

# If not, pull it:
docker compose exec ollama ollama pull mistral
```

### Make command not found (Windows PowerShell)
`make` is not available in Windows PowerShell by default.
Use **Git Bash** or run the underlying `docker compose` commands directly:
```bash
# Instead of: make fireform
docker compose build
docker compose up -d
docker compose exec ollama ollama pull mistral
```

---

## Production Deployment (Station Intranet)

For deployment on a Linux station server:

```bash
# Clone and configure
git clone https://github.com/fireform-core/FireForm
cd FireForm

# Start services
docker compose up -d
docker compose exec ollama ollama pull mistral

# FireForm is now accessible on the station intranet at:
# http://<station-server-ip>:8000
```

**HTTPS Note:** Service Workers (PWA offline mode) require HTTPS on non-localhost connections.
Most fire and police departments operate their own intranet HTTPS/SSL infrastructure —
point your department's reverse proxy (nginx/Apache) to port 8000 to enable PWA installation
on field devices without requiring cloud services or app store distribution.

---

## Architecture Overview

```
Field Devices (PWA)          Station Server (Docker)
────────────────────         ──────────────────────────────────
Officer Mobile    ──────────►  FastAPI [:8000]
Station Desktop   ──────────►    ↓ LLM extraction
Field Tablet      ──────────►  Ollama/Mistral [:11434]
                                 ↓ Structured JSON
                               Master Data Lake (SQLite/PostgreSQL)
                                 ↓ AI Semantic Mapping
                               PDF Filler (PyMuPDF)
                                 ↓
                               Filled PDF → Officer download
```

---

## Known Limitations

- **SQLite** is used by default (single-file database). For multi-station production use,
  migrate to PostgreSQL by updating `SQLMODEL_DATABASE_URL` in the environment.
- **Model download (~4GB)** is required on first run. Subsequent starts use the cached model.
- **CPU inference** is used by default. On machines with NVIDIA GPUs, Ollama automatically
  uses CUDA for faster inference — no configuration required.

---


