# ── Stage 1: Build dependencies ──────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: Runtime ─────────────────────────────────────────
FROM python:3.12-slim

# System deps for PyMuPDF (libmupdf needs these at runtime)
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libsm6 libxext6 \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY app.py config.py ./
COPY services/ services/
COPY services_v2/ services_v2/
COPY templates/ templates/
COPY static/ static/

# Create tmp + runtime data directories for file processing
RUN mkdir -p /app/tmp /app/data && chown -R appuser:appuser /app

USER appuser

EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/')" || exit 1

# Run with gunicorn (production-grade WSGI server)
# 단일 사용자 전제: 세션 상태가 모듈 전역변수라 워커/스레드 1개로 직렬화해야 안전.
# (멀티유저로 전환 시 세션키 기반 서버사이드 캐시로 재설계 후 워커 수를 늘릴 것)
CMD ["gunicorn", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "1", \
     "--threads", "1", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "app:app"]
