
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy application code
COPY . .

# Install Python dependencies after the source is present so pip can install the package itself.
RUN pip install --no-cache-dir -r requirements.txt -r requirements-ai.txt

# Set Python path so imports work correctly
ENV PYTHONPATH=/app

# Keep container running for interactive use
CMD ["tail", "-f", "/dev/null"]
