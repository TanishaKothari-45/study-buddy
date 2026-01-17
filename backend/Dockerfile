# syntax=docker/dockerfile:1.4
# ===========================================
# Study Buddy Backend - Cloud Run Dockerfile
# Optimized multi-stage build with BuildKit caching
# ===========================================

# Stage 1: Builder with cached pip installs
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    libffi-dev \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# ===========================================
# Install HEAVY packages first (rarely change, slow to install)
# This layer will be cached unless requirements-heavy.txt changes
# ===========================================
COPY requirements-heavy.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --user -r requirements-heavy.txt

# ===========================================
# Install LIGHT packages (may change more often)
# This layer rebuilds if requirements-light.txt changes
# but heavy packages layer remains cached
# ===========================================
COPY requirements-light.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --user -r requirements-light.txt

# ===========================================
# Stage 2: Production (slim runtime)
# ===========================================
FROM python:3.12-slim

WORKDIR /app

# Install runtime dependencies only (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libmagic1 \
    poppler-utils \
    curl \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy installed packages from builder to system location
# This allows the non-root user to access them
COPY --from=builder /root/.local /usr/local
# Ensure execute permissions for binaries
RUN chmod -R a+rX /usr/local/bin /usr/local/lib
ENV PATH=/usr/local/bin:$PATH

# Copy application code (separate layer for better caching)
COPY . .

# Create necessary directories and set permissions
RUN mkdir -p /app/logs /app/data/databases && \
    useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# Port configuration (8001 for local, Cloud Run will override via PORT env var)
ENV PORT=8001
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8001

# Health check for Cloud Run
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/ || exit 1

# Run with gunicorn for production
# - 2 workers for Cloud Run (CPU-bound)
# - UvicornWorker for async support
# - Timeout 300s for long-running requests
CMD exec gunicorn app.main:app \
    --workers 2 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:${PORT} \
    --timeout 300 \
    --keep-alive 30 \
    --access-logfile - \
    --error-logfile - \
    --capture-output \
    --enable-stdio-inheritance
