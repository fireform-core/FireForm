
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set Python path to project root so both src/ and api/ imports resolve correctly
ENV PYTHONPATH=/app

# Keep container running for interactive use
CMD ["tail", "-f", "/dev/null"]
