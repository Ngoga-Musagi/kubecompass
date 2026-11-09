# Backend: FastAPI + ingestion CLI. Build context: repo root.
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    KUBECOMPASS_REPO_ROOT=/app HF_HUB_DISABLE_SYMLINKS_WARNING=1
COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /usr/local/bin/uv
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/app ./app
RUN uv sync --frozen --no-dev
WORKDIR /app
COPY deployment/configuration ./deployment/configuration
COPY elasticsearch ./elasticsearch
COPY data/raw ./data/raw
COPY data/evaluation/queries.json ./data/evaluation/queries.json
RUN useradd --create-home kc && mkdir -p /app/data/processed /app/.cache && chown -R kc /app
USER kc
ENV PATH="/app/backend/.venv/bin:$PATH"
EXPOSE 8000
# Ingest on first start if Elasticsearch has no index for the conference, then serve.
CMD ["sh", "-c", "kubecompass ensure && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir /app/backend"]
