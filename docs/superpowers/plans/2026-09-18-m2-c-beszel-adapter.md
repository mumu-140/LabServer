# M2-C Implementation Plan: Beszel Primary Monitoring Adapter & Host Dashboard

Date: 2026-09-18  
Spec: `docs/superpowers/specs/2026-09-18-m2-c-beszel-adapter-design.md`  
Branch: `feat/m2-c-beszel-adapter`  
Target: `main` (commit `004cf69`, M2-B merged)

## Overview

M2-C integrates Beszel as the primary host-level monitoring source for LabServer via an edge adapter, keeping core domain models and contracts strictly decoupled from Beszel and PocketBase internals. It delivers generic host metrics contracts, a resilient Beszel HTTP adapter with TTL caching and timeout handling, a Core monitoring service and authenticated API endpoints, a responsive Web dashboard displaying the 4 primary lab servers, server seeding utilities, and updated ops runbooks.

---

## Task Breakdown

### Task 1: Monitoring Contracts & Enums
- **Files**:
  - `packages/contracts/src/labserver_contracts/monitoring.py`
  - `packages/contracts/src/labserver_contracts/__init__.py`
  - `packages/contracts/tests/test_monitoring.py`
- **Details**:
  - Define `HostStatus` (`up`, `down`, `unknown`) and `FreshnessStatus` (`fresh`, `stale`, `unreachable`, `disabled`, `unknown`).
  - Define `GpuMetricsRead`, `HostMetricsRead`, `ServerDashboardCard`, `DashboardRead`.
  - Export contracts in `labserver_contracts`.
  - Write comprehensive Pydantic serialization, validation, and immutability tests.
- **Verification**:
  - `pytest packages/contracts/tests/test_monitoring.py` passes cleanly.

### Task 2: Core Monitoring Adapter (Beszel & Fake Providers)
- **Files**:
  - `services/core/pyproject.toml` (add `httpx==0.28.1`)
  - `services/core/src/labserver_core/adapters/monitoring.py`
  - `services/core/src/labserver_core/config.py`
  - `services/core/tests/adapters/test_beszel_adapter.py`
- **Details**:
  - Define `HostMetricsProvider` protocol (`get_metrics`, `get_server_metrics`).
  - Implement `FakeHostMetricsProvider` for zero-network testing.
  - Implement `BeszelAdapter`:
    - PocketBase REST client using `httpx.AsyncClient`.
    - Authenticate via `_superusers/auth-with-password` or `users/auth-with-password`, or use `LABSERVER_BESZEL_TOKEN`.
    - Auth token caching with automatic retry on HTTP 401.
    - In-memory metrics TTL cache (default 15s) with concurrency lock.
    - System record mapping (CPU, memory %, disk %, load avg, uptime).
    - Freshness evaluation based on record `updated` timestamp.
    - Configurable key mapping (`LABSERVER_BESZEL_KEY_MAP`).
    - Robust error handling: Hub unavailability returns `UNREACHABLE` without uncaught exceptions.
  - Unit tests covering token auth, token refresh, metrics parsing, timeouts, connection errors, and caching.
- **Verification**:
  - `pytest services/core/tests/adapters/test_beszel_adapter.py` passes cleanly.

### Task 3: Core Monitoring Service & API Endpoints
- **Files**:
  - `services/core/src/labserver_core/application/monitoring_service.py`
  - `services/core/src/labserver_core/api/v1/routes/monitoring.py`
  - `services/core/src/labserver_core/api/v1/router.py`
  - `services/core/src/labserver_core/dependencies.py`
  - `services/core/tests/api/test_monitoring.py`
- **Details**:
  - Implement `MonitoringService` combining `ServerRepository`, `PlanRepository`, and `HostMetricsProvider`.
  - Implement `GET /api/v1/monitoring/dashboard` -> `DashboardRead`.
  - Implement `GET /api/v1/monitoring/servers/{server_key}` -> `HostMetricsRead`.
  - Require valid user session (members and admins).
  - Write integration tests for authenticated dashboard retrieval, server filtering, near-term plan inclusion, and 401 unauthenticated access.
- **Verification**:
  - `pytest services/core/tests/api/test_monitoring.py` passes cleanly.

### Task 4: Web Client & Dashboard Route
- **Files**:
  - `apps/web/src/labserver_web/clients/core.py`
  - `apps/web/src/labserver_web/routes/dashboard.py`
  - `apps/web/src/labserver_web/app.py`
  - `apps/web/tests/test_dashboard.py`
- **Details**:
  - Add `get_dashboard(session_token)` method to `CoreClient`.
  - Implement `GET /` and `GET /dashboard` routes in `labserver_web.routes.dashboard`.
  - Redirect unauthenticated users to `/login?next=/`.
  - Handle Core errors gracefully with user-facing message.
  - Mount router on Web application.
  - Write tests for route redirects, authenticated page loading, and error states.
- **Verification**:
  - `pytest apps/web/tests/test_dashboard.py` passes cleanly.

### Task 5: Web UI Templates & Styling
- **Files**:
  - `apps/web/src/labserver_web/templates/base.html`
  - `apps/web/src/labserver_web/templates/dashboard/index.html`
  - `apps/web/src/labserver_web/static/app.css`
- **Details**:
  - Update `base.html` header with "Dashboard" and "Schedule" navigation tabs, active state indicator, username display, and logout button.
  - Build `dashboard/index.html` rendering 4 server cards:
    - Server title, key, status badge (Up, Down, Stale, Unreachable).
    - Progress bars and values for CPU, Memory (used/total), Disk (used/total).
    - Load average and uptime.
    - Near-term active plans preview.
    - Upstream Beszel deep-link button (`[ View in Beszel ↗ ]`).
  - Add clean, responsive CSS rules for cards, gauges, badges, and navigation bar.
- **Verification**:
  - Visual check and `pytest apps/web/tests/test_dashboard.py` verifying HTML output contains cards, progress bars, and links.

### Task 6: Initial Server Seeding & Ops Integration
- **Files**:
  - `services/core/src/labserver_core/seed_servers.py`
  - `ops/seed-servers.sh`
  - `configs/examples/.env.production.example`
  - `ops/docker-compose.yml`
  - `ops/smoke-loopback.sh`
  - `docs/operations/deployment.md`
- **Details**:
  - Implement `seed_servers` script to register the 4 standard lab servers (`fwq10`, `fwq51`, `fwq56`, `fwq57`) with fleet specifications.
  - Update `ops/seed-servers.sh` wrapper.
  - Update `configs/examples/.env.production.example` with Beszel configuration variables.
  - Update `ops/docker-compose.yml` with Beszel environment mappings and optional network attachment.
  - Update `ops/smoke-loopback.sh` to include dashboard endpoint checks.
  - Update `docs/operations/deployment.md` with Beszel setup instructions.
- **Verification**:
  - Run `ops/seed-servers.sh` dry-run/unit check.

### Task 7: Container Verification, Smoke Test & Gate Finalization
- **Files**:
  - `docs/CURRENT_STATE.md`
- **Details**:
  - Run full suite in remote container via `labenv.sh`:
    - `uv sync --all-packages --dev --locked`
    - `uv run ruff check .`
    - `uv run mypy services/core/src packages/contracts/src apps/web/src`
    - `uv run pytest -q`
  - Test real Docker Compose stack on `fwq10ys`: build, seed, start, and run `ops/smoke-loopback.sh`.
  - Update `docs/CURRENT_STATE.md`.
- **Verification**:
  - All automated checks and smoke tests green on `fwq10ys`.
