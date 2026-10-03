# Deployment Guide

This guide covers deploying FireForm using Docker. By the end, you will have the full FireForm stack (FastAPI server + Ollama AI engine) running on any machine with a single command.

## Prerequisites

| Requirement | Version | Install |
| :--- | :--- | :--- |
| Docker Desktop | 26.x or newer | [docker.com/get-started](https://www.docker.com/get-started/) |
| WSL2 (Windows) | Latest | `wsl --update` |
| Git | Any | [git-scm.com](https://git-scm.com/) |
| Disk space | ~6GB free | For Docker image + Mistral model |
| RAM | 8GB min | 16GB recommended |

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
```

## Production Deployment (Station Intranet)

For deployment on a Linux station server:

1.  **Start services:** `docker compose up -d`
2.  **Pull model:** `docker compose exec ollama ollama pull mistral`
3.  **Access:** FireForm is now accessible at `http://<station-server-ip>:8000`

**HTTPS Note:** Service Workers (PWA offline mode) require HTTPS on non-localhost connections. Point your department's reverse proxy (nginx/Apache) to port 8000 to enable PWA installation.

## Known Limitations

- **SQLite** is used by default. For multi-station production use, migrate to PostgreSQL.
- **Model download (~4GB)** is required on first run.
- **CPU inference** is used by default, but Ollama will use CUDA if an NVIDIA GPU is detected.
