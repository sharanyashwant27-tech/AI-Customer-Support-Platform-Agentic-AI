# Backend API image — build from repository root:
#   docker build -f backend/Dockerfile -t aics-api:latest .
# Or via Compose (context is repo root).

FROM python:3.12-slim

LABEL org.opencontainers.image.title="AI Customer Support Platform API" \
      org.opencontainers.image.description="FastAPI multi-agent customer support API (LangGraph, RAG, GraphRAG)" \
      org.opencontainers.image.source="https://github.com/local/aics" \
      org.opencontainers.image.documentation="README.md" \
      org.opencontainers.image.licenses="Proprietary"

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    PORT=8917

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Dependencies first (better layer caching)
COPY backend/requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Application code
COPY backend/app ./app
COPY backend/run.py ./run.py
COPY backend/tests ./tests

# Project docs shipped with the image
COPY README.md ./README.md
COPY docs ./docs
COPY sample_data ./sample_data
COPY sample_prompts ./sample_prompts

EXPOSE 8917

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:8917/api/v1/health?format=raw" || \
      curl -fsS -H "Accept: application/json" "http://127.0.0.1:8917/api/v1/health" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8917"]
