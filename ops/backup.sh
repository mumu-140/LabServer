#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.yml"
TARGET_DIR="${1:-${SCRIPT_DIR}/../backups}"

mkdir -p "${TARGET_DIR}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="${TARGET_DIR}/labserver-backup-${TIMESTAMP}.db"
TMP_INSIDE="/data/.backup_${TIMESTAMP}.tmp"

echo "==> Creating consistent online SQLite backup..."
docker compose -f "${COMPOSE_FILE}" exec -T core python3 -c "
import sqlite3, sys
try:
    src = sqlite3.connect('/data/labserver.db')
    dst = sqlite3.connect('${TMP_INSIDE}')
    src.backup(dst)
    dst.close()
    src.close()
except Exception as e:
    sys.stderr.write(f'Backup failed: {e}\\n')
    sys.exit(1)
"

docker compose -f "${COMPOSE_FILE}" cp "core:${TMP_INSIDE}" "${BACKUP_FILE}"
docker compose -f "${COMPOSE_FILE}" exec -T core rm -f "${TMP_INSIDE}"

docker compose -f "${COMPOSE_FILE}" run --rm -T -v "${TARGET_DIR}:/backup:ro" core python3 -c "
import sqlite3, sys
con = sqlite3.connect('/backup/$(basename "${BACKUP_FILE}")')
res = con.execute('PRAGMA integrity_check;').fetchone()[0]
con.close()
if res != 'ok':
    sys.stderr.write(f'Integrity check failed: {res}\\n')
    sys.exit(1)
print('Integrity check passed: ok')
"

BACKUP_SIZE="$(ls -lh "${BACKUP_FILE}" | awk '{print $5}')"
echo "==> Backup successfully created: ${BACKUP_FILE} (${BACKUP_SIZE})"
