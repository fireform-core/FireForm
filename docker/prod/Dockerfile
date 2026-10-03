# ---- builder ----
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential g++ libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /build
COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache/uv \
    UV_TORCH_BACKEND=cpu \
    uv pip install --system -r requirements.txt

# ---- runtime ----
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgl1 \
    libglib2.0-0 \
    libxcb1 \
    libpq5 && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY app/ ./app/
COPY requirements.txt .
COPY docker/entrypoint.sh /entrypoint.sh

# Bake deps hash so the entrypoint can skip the redundant install when unchanged.
RUN sha256sum requirements.txt | cut -d' ' -f1 > /opt/req_hash

ENV PYTHONPATH=/app

RUN mkdir -p /data/db /data/uploads && chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "app.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
