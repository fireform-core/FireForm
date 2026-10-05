# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

# apt cache mounts keep downloaded .debs across builds
RUN rm -f /etc/apt/apt.conf.d/docker-clean; echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt \
    apt-get update && apt-get install -y \
    curl \
    libgl1 \
    libglib2.0-0 \
    libxcb1 \
    libpq-dev \
    build-essential \
    g++

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache/uv \
    UV_TORCH_BACKEND=cpu \
    uv pip install --system -r requirements.txt

# Bake a hash of the deps the image was built with. The entrypoint compares this
# against the live (bind-mounted) requirements.txt to decide whether to reinstall.
RUN sha256sum requirements.txt | cut -d' ' -f1 > /opt/req_hash

ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
