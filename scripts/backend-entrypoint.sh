#!/usr/bin/env sh
set -eu

mkdir -p /app/backend/data
export PYTHONPATH=/app/backend

cd /app
alembic -c backend/alembic.ini upgrade head
exec uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips="*"
