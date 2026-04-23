# ── Store Intelligence API ──────────────────────────────────────────
# Build:  docker compose up -d --build
# Test:   docker compose exec api pytest tests/ -v --cov=app
# ────────────────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# System deps for OpenCV + psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc g++ \
    libglib2.0-0 libsm6 libxrender1 libxext6 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer cache)
COPY app/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY app/ ./app/
COPY infra/ ./infra/
COPY pipeline/ ./pipeline/
COPY tests/ ./tests/
COPY pytest.ini .

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

# Built-in health probe (used by docker compose healthcheck)
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
