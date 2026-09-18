#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.yml"

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <username> [--promote]"
    exit 1
fi

if docker compose -f "${COMPOSE_FILE}" ps --status running core | grep -q core; then
    docker compose -f "${COMPOSE_FILE}" exec -T core python -m labserver_core.bootstrap_admin "$@"
else
    docker compose -f "${COMPOSE_FILE}" run --rm -T core python -m labserver_core.bootstrap_admin "$@"
fi
