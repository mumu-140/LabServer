# M2-B Implementation Plan: Docker-First Deployment Form

Date: 2026-09-18  
Spec: `docs/superpowers/specs/2026-09-18-m2-b-deployment-form-design.md`  
Branch: `feat/m2-b-deployment-form`  
Target: `main` (commit `e8a41b5`, M2-A merged)

## Overview

M2-B packages LabServer as a production-grade Docker Compose stack on `fwq10ys`, with automated database migrations, non-root user permissions, explicit `/24` subnet isolation, `127.0.0.1` loopback bindings, safe environment configuration templates, backup/restore procedures, and an end-to-end loopback smoke test.

## Task Breakdown

### Task 1: Production Multi-stage Dockerfile & Core Entrypoint
- Files:
  - `ops/Dockerfile`
  - `ops/entrypoint-core.sh`
- Details:
  - Multi-stage build (`python:3.13-slim` + `uv` from official image).
  - Builds workspace with `uv sync --frozen --no-dev`.
  - Non-root runtime user `labserver` (UID 1000).
  - `ops/entrypoint-core.sh`: ensures `/data` permissions, runs `alembic upgrade head`, and execs `uvicorn labserver_core.app:app`.
- Verification:
  - Build image on `fwq10ys`: `docker build -f ops/Dockerfile -t labserver:local .` succeeds.

### Task 2: Docker Compose Specification & Safe Environment Template
- Files:
  - `ops/docker-compose.yml`
  - `configs/examples/.env.production.example`
- Details:
  - Compose services: `core` and `web`.
  - `labserver-net` bridge network with fixed subnet `10.255.30.0/24`.
  - Volumes: `./data:/data` mounted to `core`.
  - Port publishing: `127.0.0.1:18280:8000` for `web`, optional `127.0.0.1:18281:8000` for `core`.
  - Health checks: `core` via `curl -f http://127.0.0.1:8000/healthz`, `web` depends on `core` with `service_healthy`.
  - Safe `.env.production.example` documenting `LABSERVER_SECRET_KEY`, `LABSERVER_COOKIE_SECURE`, `LABSERVER_TIMEZONE`, etc.
- Verification:
  - `docker compose -f ops/docker-compose.yml config` validates without errors.

### Task 3: Operations Tooling (Admin Bootstrap, Backup, Restore)
- Files:
  - `ops/bootstrap-admin.sh`
  - `ops/backup.sh`
  - `ops/restore.sh`
- Details:
  - `ops/bootstrap-admin.sh`: executes `python -m labserver_core.bootstrap_admin` inside running `core` container.
  - `ops/backup.sh`: uses SQLite online backup API (`.backup`) to create non-blocking point-in-time snapshots in `./backups/`.
  - `ops/restore.sh`: stops containers, validates backup file, restores database, and restarts containers.
- Verification:
  - Executable permissions set, unit/dry-run checks pass.

### Task 4: Deployment Operations Runbook & Harness Guide
- Files:
  - `docs/operations/deployment.md`
  - `docs/harnesses/ops.md`
- Details:
  - Document prerequisites, initial deployment steps, admin credential generation, upgrade/rollback protocol, and disaster recovery.
  - Update `docs/harnesses/ops.md` to reflect active ops harness assets and commands.
- Verification:
  - Documentation links and commands accurate.

### Task 5: End-to-End Loopback Smoke Verification
- Files:
  - `ops/smoke-loopback.sh`
- Details:
  - Script performs end-to-end smoke verification against `http://127.0.0.1:18280`:
    - Core `/healthz` check;
    - Web `/schedule` render check;
    - Web `/login` check;
    - Bootstrap admin execution;
    - Web login with generated credentials;
    - Authenticated `/schedule` and `/api/v1/auth/me` checks;
    - Logout and session invalidation check.
- Verification:
  - Execute `docker compose -f ops/docker-compose.yml up -d` on `fwq10ys`.
  - Run `ops/smoke-loopback.sh` -> all checks pass.
  - Cleanly tear down ephemeral deployment test container/volumes.

### Task 6: Documentation & Gate Finalization
- Files:
  - `docs/CURRENT_STATE.md`
- Details:
  - Record M2-B completion and open the gate for M2-C (Beszel primary monitoring).
- Verification:
  - Full container test suite: `labenv.sh "uv run pytest -q && uv run mypy ... && uv run ruff check ."`.
  - Secret scan & private network check.
