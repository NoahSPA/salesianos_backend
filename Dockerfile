# =============================================================================
# Salesianos FC API - Production Dockerfile
# =============================================================================
# Multi-stage, non-root, healthcheck. CMD en forma exec (sin shell) para
# que gunicorn sea PID 1 y reciba señales correctamente.
# =============================================================================

# --- Build ---
FROM python:3.12-slim AS builder

LABEL maintainer="Salesianos FC"
LABEL org.opencontainers.image.title="Salesianos FC API"
LABEL org.opencontainers.image.description="API gestión equipo fútbol amateur"
LABEL org.opencontainers.image.vendor="Noah IT"

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libmagic1 \
    libmagic-dev \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt ./

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

RUN find /usr/local/lib/python3.12/site-packages -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true && \
    find /usr/local/lib/python3.12/site-packages -name "*.pyc" -delete 2>/dev/null || true

# --- Runtime ---
FROM python:3.12-slim AS runtime

LABEL maintainer="Salesianos FC"
LABEL org.opencontainers.image.title="Salesianos FC API"
LABEL org.opencontainers.image.description="API gestión equipo fútbol amateur"
LABEL org.opencontainers.image.vendor="Noah IT"

RUN groupadd -r appuser --gid=1000 && \
    useradd -r -g appuser --uid=1000 --create-home --shell /bin/bash appuser

# CA certs y OpenSSL para TLS con MongoDB Atlas (evitar "SSL handshake failed: tlsv1 alert internal error")
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    libmagic1 \
    ca-certificates \
    openssl \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && apt-get autoremove -y

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --chown=appuser:appuser . .

RUN mkdir -p /app/logs /app/tmp && \
    chown -R appuser:appuser /app && \
    chmod -R 755 /app

USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

EXPOSE 8000

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Forma exec: gunicorn es PID 1, sin shell intermedio. Variables de entorno
# se pasan desde docker-compose o .env.
CMD ["gunicorn", "app.main:app", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--keep-alive", "5", \
     "--max-requests", "1000", \
     "--max-requests-jitter", "100", \
     "--preload", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--log-level", "info"]
