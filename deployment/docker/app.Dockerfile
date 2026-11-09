# Single-container KubeCompass (web UI + API) for public hosting: Hugging Face Spaces, Render,
# Google Cloud Run, Koyeb… Build context: repo root.
#   docker build -f deployment/docker/app.Dockerfile -t kubecompass-app .
# Data lives in Elasticsearch (e.g. Elastic Cloud); configure it with environment variables/secrets.

# ---- web: Next.js standalone, calling the API on the same origin ----------------------------
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
ENV NEXT_PUBLIC_API_URL="" BACKEND_INTERNAL_URL=http://127.0.0.1:8000 NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ---- runtime: Python API + Node web server -----------------------------------------------------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    KUBECOMPASS_REPO_ROOT=/app HF_HUB_DISABLE_SYMLINKS_WARNING=1 NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production PORT=7860
COPY --from=node:22-slim /usr/local/bin/node /usr/local/bin/node
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
COPY --from=web /web/.next/standalone ./web
COPY --from=web /web/.next/static ./web/.next/static
COPY --from=web /web/public ./web/public
COPY deployment/docker/app-start.sh /usr/local/bin/app-start
RUN chmod +x /usr/local/bin/app-start && useradd -m -u 1000 kc \
    && mkdir -p /app/data/processed /app/.cache && chown -R kc /app
USER 1000
ENV PATH="/app/backend/.venv/bin:$PATH"
EXPOSE 7860
CMD ["app-start"]
