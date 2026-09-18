#!/bin/sh
set -e

if [ -z "$LABSERVER_DATABASE_URL" ]; then
    export LABSERVER_DATABASE_URL="sqlite:////data/labserver.db"
fi

mkdir -p /data

echo "==> Running database migrations..."
alembic -c /app/services/core/alembic.ini upgrade head

echo "==> Starting Core service..."
if [ "$#" -gt 0 ]; then
    exec "$@"
else
    exec uvicorn labserver_core.app:app --host 0.0.0.0 --port 8000
fi
