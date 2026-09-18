# M2-B: Docker-First Deployment Form Design

Date: 2026-09-18  
Status: Proposed  
Branch: feat/m2-b-deployment-form  
Target baseline: main (commit e8a41b5, M2-A merged)

## 1. Context & Motivation

With M1.1 (simple planning), M1.1H (web hardening), and M2-A (production human auth adapter) merged and verified on `main`, LabServer has a complete, working planning domain and authenticated web surface with 187 passing automated tests.

However, the software currently only runs in ephemeral development test suites and containerized test runners (`labenv.sh`). To make it usable as an operational service while strictly adhering to repository and infrastructure rules, M2-B establishes the production deployment form:
- Containerized packaging via Docker;
- Deterministic orchestration via Docker Compose;
- Non-root runtime with persistent volume management for SQLite;
- Rigid network isolation with fixed small `/24` subnet and `127.0.0.1` loopback bindings;
- Safe environment templates and operational runbooks for initial bootstrap, backup, and health checks.

## 2. In Scope vs Explicit Non-Goals

### In Scope
1. **Packaging**: Unified, reproducible multi-stage `ops/Dockerfile` utilizing `python:3.13-slim` and `uv` to install locked workspace dependencies.
2. **Orchestration**: `ops/docker-compose.yml` defining `core` and `web` service containers.
3. **Data Management**: Dedicated `./data` volume for SQLite database (`labserver.db`) and WAL files, run as non-root user (UID 1000).
4. **Automated Migration & Health**: Automatic `alembic upgrade head` in Core entrypoint; native Docker healthchecks for both Core and Web.
5. **Network Hardening**:
   - Explicit Docker network `labserver-net` with fixed subnet `10.255.30.0/24` (avoiding `172.16.0.0/12` conflicts per fleet rule).
   - Core API bound to internal Docker network (and optionally loopback `127.0.0.1:18281`).
   - Web service strictly bound to loopback `127.0.0.1:18280`.
6. **Environment Templates**: Safe `configs/examples/.env.production.example` containing placeholders only.
7. **Ops Tooling**:
   - `ops/bootstrap-admin.sh`: Initial admin user credential generator wrapping `python -m labserver_core.bootstrap_admin`.
   - `ops/smoke-loopback.sh`: Host-side curl loopback verification script.
   - `ops/backup.sh` & `ops/restore.sh`: Safe SQLite backup/restore utilities.
8. **Runbooks**: `docs/operations/deployment.md` covering initial deployment, bootstrap, upgrade, and rollback.

### Explicit Non-Goals
- **No Public Reverse-Proxy Mount**: Caddy host configuration and Cloudflare tunnel bindings on `fwq10ys` are out of scope for M2-B (isolated to a separate approved change after M2-B verification).
- **No Telemetry / Beszel Integration**: Host metrics integration remains M2-C.
- **No Runtime Collector**: Agent process monitoring remains M2-D.
- **No Job Scheduler or Process Control**: Core remains planning and observation only.

## 3. Architecture & Container Topology

```text
[ Host Loopback 127.0.0.1 ]
       |
       +---> 127.0.0.1:18280 ---> [ Container: labserver-web ] (Port 8000)
       |                                     |
       |                              Docker Network:
       |                           10.255.30.0/24 (labserver-net)
       |                                     |
       |                                     v
       +---> 127.0.0.1:18281 ---> [ Container: labserver-core ] (Port 8000)
       (optional diagnostic)                 |
                                     Volume Mount:
                                  ./data -> /data (labserver.db)
```

### Component Roles

1. **`labserver-core`**:
   - Entrypoint: `ops/entrypoint-core.sh` (runs `alembic upgrade head` then execs `uvicorn labserver_core.app:app --host 0.0.0.0 --port 8000`).
   - Environment:
     - `LABSERVER_DATABASE_URL=sqlite:////data/labserver.db`
     - `LABSERVER_ENV=production`
     - `LABSERVER_SECRET_KEY=${LABSERVER_SECRET_KEY}`
     - `LABSERVER_TIMEZONE=${LABSERVER_TIMEZONE:-Asia/Shanghai}`
     - `LABSERVER_COOKIE_SECURE=${LABSERVER_COOKIE_SECURE:-false}`
   - Healthcheck: `GET http://127.0.0.1:8000/healthz` -> HTTP 200 `{"status": "ok"}`.
   - Volume: `./data:/data` (persists SQLite database).

2. **`labserver-web`**:
   - Entrypoint: `uvicorn labserver_web.app:app --host 0.0.0.0 --port 8000`.
   - Depends on: `core` with `condition: service_healthy`.
   - Environment:
     - `LABSERVER_CORE_BASE_URL=http://core:8000`
     - `LABSERVER_TIMEZONE=${LABSERVER_TIMEZONE:-Asia/Shanghai}`
     - `LABSERVER_COOKIE_SECURE=${LABSERVER_COOKIE_SECURE:-false}`
   - Healthcheck: `GET http://127.0.0.1:8000/healthz` or `GET http://127.0.0.1:8000/login` -> HTTP 200.
   - Port mapping: `127.0.0.1:18280:8000`.

## 4. Packaging Strategy (`ops/Dockerfile`)

A multi-stage build keeping final image small, secure, and reproducible:
- **Builder Stage**:
  - Base: `python:3.13-slim`
  - Installs `uv` via `COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv`
  - Copies `pyproject.toml`, `uv.lock`, packages and services source code.
  - Runs `uv sync --frozen --no-dev --no-install-project` followed by `uv sync --frozen --no-dev`.
- **Runtime Stage**:
  - Base: `python:3.13-slim`
  - Creates non-root system user `labserver` (UID 1000, GID 1000).
  - Copies virtual environment `.venv` and application code from builder stage.
  - Sets `PATH="/app/.venv/bin:$PATH"`.
  - Installs minimal runtime tools: `curl` (for healthchecks) and `sqlite3` (for backup verification).
  - Sets default working directory `/app` and switches to user `labserver`.

## 5. Storage, Backup, and Permissions

- **Host Directory**: `./data` on host mapped to `/data` in `core` container.
- **SQLite WAL Mode**: Migration/connection strings use WAL journaling for high concurrent read/write throughput without table lock starvation.
- **Permissions**: Container user `labserver` (UID 1000) matches default host user `yangs` (UID 1000) on `fwq10ys`, preventing permissions mismatch on bind-mounted files.
- **Backup Script (`ops/backup.sh`)**: Uses `sqlite3 /data/labserver.db ".backup /backup/labserver-backup-$(date +%Y%m%d%H%M%S).db"` inside the container to ensure non-blocking, transactionally consistent online backups without stopping the service.

## 6. Host Integration & VPS Invariants

- **Zero Host Pollution**: No dependencies installed on host Python.
- **Port Assignment**:
  - Web: `127.0.0.1:18280` (verified free on `fwq10ys`).
  - Core: `127.0.0.1:18281` (optional direct loopback access for CLI / diagnostic).
- **Subnet Assignment**:
  - `10.255.30.0/24` (verified free from host route conflicts).
- **Loopback-Only Boundary**:
  - No `0.0.0.0` or public interface binding.
  - Caddy integration deferred until after full M2-B verification.
