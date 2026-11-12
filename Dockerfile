# Single-container build: the FastAPI app serves the built React frontend.
FROM node:22-alpine AS web
WORKDIR /web
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM python:3.12-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 \
    STATIC_DIR=/app/static DATABASE_URL=sqlite:////data/decisionflow.db
COPY --from=ghcr.io/astral-sh/uv:0.12.7 /uv /usr/local/bin/uv
RUN useradd --create-home app && mkdir /data && chown app /data
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./
COPY --from=web /web/dist ./static
COPY docker-entrypoint.sh /usr/local/bin/
USER app
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')"
ENTRYPOINT ["docker-entrypoint.sh"]
