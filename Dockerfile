# JARVIS 24/7 Always-On Cloud Backend
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install lightweight cloud dependencies
COPY cloud_deploy/requirements-cloud.txt .
RUN pip install --no-cache-dir -r requirements-cloud.txt

# Copy JARVIS core application code
COPY jarvis ./jarvis
COPY .env.example .env

# Create persistent data and cache directories
RUN mkdir -p /app/data /app/.cache

ENV OPENJARVIS_HOME=/app
ENV PORT=8000
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Start Uvicorn with dynamic cloud PORT, proxy header support, and zero desktop dependencies
CMD ["sh", "-c", "uvicorn jarvis.cloud_server:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
