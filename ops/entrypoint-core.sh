#!/bin/sh
set -e

if [ -z "$LABSERVER_DATABASE_URL" ]; then
    export LABSERVER_DATABASE_URL="sqlite:////data/labserver.db"
fi

mkdir -p /data

echo "==> Running database migrations..."
python3 -c "
import os, sys
from alembic import command
from alembic.config import Config

cfg = Config('/app/services/core/alembic.ini')
db_url = os.environ.get('LABSERVER_DATABASE_URL')
if db_url:
    cfg.set_main_option('sqlalchemy.url', db_url)
cfg.set_main_option('sqlalchemy.isolation_level', 'AUTOCOMMIT')
command.upgrade(cfg, 'head')
print('==> Migrations upgraded to head successfully.')
"

echo "==> Starting Core service..."
if [ "$#" -gt 0 ]; then
    exec "$@"
else
    exec uvicorn labserver_core.app:app --host 0.0.0.0 --port "${PORT:-18281}"
fi
