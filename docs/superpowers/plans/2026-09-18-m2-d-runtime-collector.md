# M2-D Implementation Plan: Minimal Read-Only Runtime Collector & "Running" View

Date: 2026-09-18  
Spec: `docs/superpowers/specs/2026-09-18-m2-d-runtime-collector-design.md`  
Branch: `feat/m2-d-runtime-collector`  
Target: `main` (commit `43490c4`, M2-C merged)

## Overview

M2-D implements the minimal read-only Runtime Collector and "Running" Web view for LabServer. It bridges the gap between host-level telemetry (Beszel) and published user intent (LabServer plans) by inspecting active GPU processes (PID, name, user attribution, memory) on compute hosts (`fwq57`, `fwq51`), correlating them in Core with active `ONGOING` plans, and surfacing a clear, informative "Running" view in the Web UI.

---

## Task Breakdown

### Task 1: Runtime Contracts & Enums
- **Files**:
  - `packages/contracts/src/labserver_contracts/runtime.py`
  - `packages/contracts/src/labserver_contracts/__init__.py`
  - `packages/contracts/tests/test_runtime.py`
- **Details**:
  - Define `RuntimeStatus` (`active`, `idle`, `unavailable`).
  - Define `RuntimePlanCorrelation` (`matched`, `unplanned`, `idle_reservation`).
  - Define Pydantic models: `GpuProcessInfo`, `GpuDeviceRuntime`, `HostRuntimeReport`, `HostRuntimeRead`, `RuntimeOverviewRead`.
  - Export models in `packages/contracts/src/labserver_contracts/__init__.py`.
  - Add unit tests verifying serialization, default values, and schema validation.
- **Verification**:
  - `pytest packages/contracts/tests/test_runtime.py` passes cleanly.

### Task 2: Core Runtime Store & Correlation Service
- **Files**:
  - `services/core/src/labserver_core/application/runtime_store.py`
  - `services/core/src/labserver_core/application/runtime_service.py`
  - `services/core/src/labserver_core/config.py`
  - `services/core/tests/unit/test_runtime_service.py`
- **Details**:
  - Implement in-memory thread-safe `RuntimeStore` with configurable TTL (default: 120s) and freshness tracking.
  - Implement `RuntimeService`:
    - `submit_report(report: HostRuntimeReport)`: updates runtime store for server.
    - `get_overview()`: aggregates runtime snapshots across all managed servers.
    - `get_server_runtime(server_key)`: retrieves runtime for a specific server.
    - Correlation logic: cross-reference GPU processes against `PlanRepository` active ongoing plans for `(server_id, now)`. Matches process username against plan owner username; marks `MATCHED` or `UNPLANNED`. Detects `IDLE_RESERVATION` where plans exist but GPUs are idle.
  - Add `LABSERVER_COLLECTOR_TOKEN` to `Settings`.
  - Write unit tests for store expiry, plan correlation, user matching, and fallback states.
- **Verification**:
  - `pytest services/core/tests/unit/test_runtime_service.py` passes cleanly.

### Task 3: Core Runtime API Endpoints
- **Files**:
  - `services/core/src/labserver_core/api/routes/runtime.py`
  - `services/core/src/labserver_core/api/dependencies.py`
  - `services/core/src/labserver_core/api/router.py`
  - `services/core/src/labserver_core/app.py`
  - `services/core/tests/api/test_runtime.py`
- **Details**:
  - Implement `POST /api/v1/runtime/report`: collector ingress with bearer token authentication (`X-Collector-Token` or `Authorization: Bearer <token>`).
  - Implement `GET /api/v1/runtime/overview`: member/admin authenticated endpoint returning `RuntimeOverviewRead`.
  - Implement `GET /api/v1/runtime/servers/{server_key}`: member/admin authenticated endpoint returning `HostRuntimeRead`.
  - Mount runtime router on Core application.
  - Write integration tests for collector submission, unauthenticated rejection (401/403), viewer access, and 404 for unknown servers.
- **Verification**:
  - `pytest services/core/tests/api/test_runtime.py` passes cleanly.

### Task 4: Lightweight Host Collector Script
- **Files**:
  - `ops/labserver-collector.py`
  - `tests/unit/test_collector.py` (or `ops/tests/test_collector.py`)
- **Details**:
  - Implement pure-Python 3 standard library script `ops/labserver-collector.py`:
    - CLI arguments: `--server-key`, `--core-url`, `--token`, `--timeout`, `--dry-run`.
    - Query `nvidia-smi` for GPU indices, names, memory, utilization, temperature.
    - Query `nvidia-smi` compute apps for running PIDs and GPU memory.
    - Query `ps` for process owner usernames.
    - Graceful non-GPU host fallback: if `nvidia-smi` is not installed or fails, reports empty GPU list.
    - POST JSON payload to Core `POST /api/v1/runtime/report`.
  - Add unit test with mocked subprocess outputs to verify parsing and error resilience.
- **Verification**:
  - Test collector script dry-run on `fwq10ys` and `fwq57ys`.

### Task 5: Web Client, "Running" Route & View UI
- **Files**:
  - `apps/web/src/labserver_web/clients/core.py`
  - `apps/web/src/labserver_web/routes/running.py`
  - `apps/web/src/labserver_web/app.py`
  - `apps/web/src/labserver_web/templates/base.html`
  - `apps/web/src/labserver_web/templates/running/index.html`
  - `apps/web/src/labserver_web/static/app.css`
  - `apps/web/tests/conftest.py`
  - `apps/web/tests/test_running.py`
- **Details**:
  - Add `get_runtime_overview(session_token)` to `CoreClient` and `FakeCoreClient`.
  - Implement `GET /running` in `labserver_web.routes.running`:
    - Unauthenticated default-deny redirect to `/login?next=/running`.
    - Renders `running/index.html`.
  - Update `base.html` navigation with "Running" tab between "Dashboard" and "Schedule".
  - Template `running/index.html`:
    - Server overview cards.
    - GPU device cards (model, index, memory gauge, temperature).
    - Active GPU process table (Host, GPU ID, PID, Process Name, User, GPU Memory, Booking Status Badge: `Matched`, `Unplanned`, `Idle`).
  - Add CSS styles for process tables, badges, and device gauges.
  - Write web tests for anonymous redirect, authenticated rendering, and empty/error states.
- **Verification**:
  - `pytest apps/web/tests/test_running.py` passes cleanly.

### Task 6: Ops Configuration & Loopback Smoke Test
- **Files**:
  - `configs/examples/.env.production.example`
  - `ops/docker-compose.yml`
  - `ops/smoke-loopback.sh`
  - `docs/operations/deployment.md`
- **Details**:
  - Add `LABSERVER_COLLECTOR_TOKEN` to `.env.production.example` and `ops/docker-compose.yml`.
  - Update `ops/smoke-loopback.sh`:
    - Test unauthenticated `GET /running` (401).
    - Submit sample runtime report via curl / collector script to `/api/v1/runtime/report`.
    - Verify authenticated `GET /api/v1/runtime/overview` returns reported GPUs and processes.
    - Verify authenticated Web `GET /running` renders GPU and process table.
  - Update deployment documentation with collector setup instructions.
- **Verification**:
  - `./ops/smoke-loopback.sh` passes on `fwq10ys` with full container stack.

### Task 7: Full CI Verification, PR & Merge
- **Files**:
  - `docs/CURRENT_STATE.md`
- **Details**:
  - Run full suite in `labenv.sh` on `fwq10ys`:
    - `uv sync --all-packages --dev --locked`
    - `uv run ruff check .`
    - `uv run mypy services/core/src packages/contracts/src apps/web/src`
    - `uv run pytest -q`
  - Update `docs/CURRENT_STATE.md`.
  - Push branch to GitHub, open PR #11, verify CI green, squash-merge into `main`.
  - Sync remote repo on `fwq10ys` and update `servers/fwq10ys.md`.
- **Verification**:
  - All checks green, merged to main, server ledger updated.
