
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
# Fixes #275 #191 #184 — libGL and libglib2 required by faster-whisper / OpenCV
# Fixes #53 — libxcb1 missing from python:3.11-slim base image
# ffmpeg required by faster-whisper for audio processing
RUN apt-get update && apt-get install -y \
    curl \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    libxcb1 \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Fix #118 #116 — PYTHONPATH must be /app (project root), not /app/src
# All imports use api.*, src.* which require the root to be on the path
ENV PYTHONPATH=/app

# Expose FastAPI port
EXPOSE 8000

# Start the FastAPI server (not tail -f /dev/null which does nothing)
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
