#!/bin/sh
set -e
if [ "$RUN_DB_MIGRATIONS" = "1" ]; then
  python scripts/apply_migrations.py
fi
exec uvicorn main:app --host 0.0.0.0 --port 8000
