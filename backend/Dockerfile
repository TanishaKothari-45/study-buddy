# syntax=docker/dockerfile:1.4
# ===========================================
# Study Buddy Backend - Cloud Run Dockerfile
# Uses pre-built base image for fast builds (~2-3 min)
# ===========================================
# IMPORTANT: First build the base image:
#   gcloud builds submit --config=cloudbuild-base.yaml --region=asia-south1
# ===========================================

# Use the pre-built base image with all Python dependencies
ARG REGION=asia-south1
ARG PROJECT_ID
ARG REPO=study-buddy
FROM ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/backend-base:latest

WORKDIR /app

# Copy application code only (dependencies are in base image)
COPY . .

# Ensure correct ownership (appuser was created in base image)
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Port configuration (8001 for local, Cloud Run will override via PORT env var)
ENV PORT=8001

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
