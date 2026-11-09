# Real-time ECG Heartbeat Classification Pipeline — Dockerfile
FROM python:3.10-slim

# Avoid interactive prompts during apt install
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and resources
COPY source_code/ ./source_code/

WORKDIR /app/source_code

# Expose Web dashboard port
EXPOSE 8501

# Default command: run HTML/CSS/Flask dashboard
CMD ["python", "app.py"]
