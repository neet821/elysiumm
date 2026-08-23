#!/usr/bin/env sh
set -eu

python /app/run_migrations.py
exec uvicorn main:app --host 0.0.0.0 --port 8000
