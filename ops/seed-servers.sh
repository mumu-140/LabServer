#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.yml"

if docker compose -f "${COMPOSE_FILE}" ps --status running core | grep -q core; then
    docker compose -f "${COMPOSE_FILE}" exec -T core python -m labserver_core.seed_servers "$@"
else
    docker compose -f "${COMPOSE_FILE}" run --rm -T core python -m labserver_core.seed_servers "$@"
fi
