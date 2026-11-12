#!/bin/sh
set -e
cd /app
.venv/bin/alembic upgrade head
.venv/bin/python -m app.seed   # no-op when data already exists
exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers
