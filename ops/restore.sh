#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.yml"

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <backup_file.db> [--yes]"
    exit 1
fi

BACKUP_FILE="$1"
CONFIRM="${2:-}"

if [ ! -f "${BACKUP_FILE}" ]; then
    echo "Error: Backup file not found: ${BACKUP_FILE}"
    exit 1
fi

echo "==> Verifying backup file integrity..."
docker compose -f "${COMPOSE_FILE}" run --rm -T -v "$(cd "$(dirname "${BACKUP_FILE}")" && pwd):/backup:ro" core python3 -c "
import sqlite3, sys
con = sqlite3.connect('/backup/$(basename "${BACKUP_FILE}")')
res = con.execute('PRAGMA integrity_check;').fetchone()[0]
con.close()
if res != 'ok':
    sys.stderr.write(f'Integrity check failed: {res}\\n')
    sys.exit(1)
print('Backup integrity: ok')
"

if [ "${CONFIRM}" != "--yes" ] && [ "${CONFIRM}" != "-y" ]; then
    echo "WARNING: This will replace the active SQLite database with ${BACKUP_FILE}."
    echo "Existing database will be preserved as .pre-restore archive."
    read -r -p "Proceed with restore? [y/N] " response
    if [[ ! "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        echo "Restore aborted by user."
        exit 0
    fi
fi

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
echo "==> Stopping application services..."
docker compose -f "${COMPOSE_FILE}" stop core web

echo "==> Preserving pre-restore live database..."
docker compose -f "${COMPOSE_FILE}" run --rm -T core python3 -c "
import os, shutil
if os.path.exists('/data/labserver.db'):
    shutil.copy2('/data/labserver.db', f'/data/labserver.db.pre-restore-${TIMESTAMP}')
"

echo "==> Restoring database from snapshot..."
docker compose -f "${COMPOSE_FILE}" run --rm -T -v "$(cd "$(dirname "${BACKUP_FILE}")" && pwd):/backup:ro" core python3 -c "
import shutil, glob, os
shutil.copy2('/backup/$(basename "${BACKUP_FILE}")', '/data/labserver.db')
for stale in glob.glob('/data/labserver.db-wal') + glob.glob('/data/labserver.db-shm'):
    if os.path.exists(stale):
        os.remove(stale)
print('Restored database file successfully.')
"

echo "==> Restarting application services..."
docker compose -f "${COMPOSE_FILE}" start core web

echo "==> Waiting for core healthcheck..."
sleep 3
docker compose -f "${COMPOSE_FILE}" exec -T core python3 -c "
import urllib.request
resp = urllib.request.urlopen('http://127.0.0.1:18281/healthz')
assert resp.status == 200
print('Core health status: 200 OK')
"

echo "==> Database restore completed successfully."
