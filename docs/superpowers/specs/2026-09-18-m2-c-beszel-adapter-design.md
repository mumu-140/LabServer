# M2-C: Beszel Primary Monitoring Adapter & Host Dashboard Design

Date: 2026-09-18  
Status: Proposed  
Branch: feat/m2-c-beszel-adapter  
Target baseline: main (commit 004cf69, M2-B merged)

## 1. Context & Motivation

With M2-A (production human authentication adapter) and M2-B (Docker-first deployment form) merged into `main`, LabServer possesses a containerized, production-ready foundation with persistent SQLite storage, strict network isolation, automated migrations, and comprehensive operations runbooks.

However, LabServer currently presents only the planning and schedule surface (`/schedule`). As established in the system architecture specification (`docs/superpowers/specs/2026-09-15-labserver-design.md` §5.1, §11, §13):
- LabServer must **not** duplicate a full time-series monitoring or telemetry platform.
- **Beszel** is the primary upstream monitoring baseline for host-level CPU, memory, disk, network, load, uptime, and alerting.
- Monitoring integrations must be **adapters at the edge**: Beszel-specific types, PocketBase schemas, and collection structures must never leak into core domain interfaces.
- The Core service and Web dashboard must be fully testable without network access, without a running Beszel instance, and without physical servers or GPUs.
- An unavailable host or unreachable Beszel Hub must **never** take down LabServer or disrupt coordination.

Milestone M2-C delivers:
1. Generic, vendor-agnostic host monitoring contracts in `packages/contracts`.
2. A resilient Beszel adapter in `services/core` communicating with Beszel Hub (PocketBase REST API), featuring in-memory TTL caching, connection timeout bounds, graceful error fallback, and test doubles.
3. Core monitoring service and authenticated API endpoints (`/api/v1/monitoring/dashboard` and `/api/v1/monitoring/servers/{key}`).
4. An authenticated, responsive Web Dashboard (`/` and `/dashboard`) displaying the 4 primary lab servers (`fwq10`, `fwq51`, `fwq56`, `fwq57`) with live status indicators, resource bars, near-term reservation pressure, and deep-links to upstream Beszel history.
5. Server seeding utilities and updated deployment templates/runbooks.

---

## 2. In Scope vs Explicit Non-Goals

### In Scope
1. **Contracts**:
   - `HostStatus` enum (`up`, `down`, `unknown`).
   - `FreshnessStatus` enum (`fresh`, `stale`, `unreachable`, `disabled`, `unknown`).
   - `GpuMetricsRead` model for GPU summary metrics (best-effort).
   - `HostMetricsRead` normalized data transfer object.
   - `ServerDashboardCard` uniting server capacity specs, host live metrics, and near-term plan count.
   - `DashboardRead` DTO for the dashboard view.
2. **Core Monitoring Adapter**:
   - `HostMetricsProvider` protocol.
   - `BeszelAdapter` implementing `HostMetricsProvider`:
     - PocketBase REST client (`httpx.AsyncClient`) supporting superuser / user password authentication and pre-shared token.
     - Auth token caching with automatic re-auth on 401.
     - In-memory metrics TTL cache (default 15s) with background refresh lock.
     - Configurable connect/read timeouts (default 5s).
     - Configurable logical key mapping (`LABSERVER_BESZEL_KEY_MAP`).
     - Freshness calculation based on record `updated` timestamp vs configurable freshness threshold (default 120s).
     - Deep-link upstream URL generation (`{PUBLIC_URL}/system/{name}`).
     - Safe fallback: unreachable Hub or missing system yields `unreachable` / `unknown` status without raising unhandled exceptions.
   - `FakeHostMetricsProvider` for deterministic, zero-network unit/API testing.
3. **Core Monitoring Service & API**:
   - `MonitoringService` combining `ServerRepository`, `HostMetricsProvider`, and `PlanRepository`.
   - `GET /api/v1/monitoring/dashboard` endpoint returning `DashboardRead`.
   - `GET /api/v1/monitoring/servers/{server_key}` endpoint returning `HostMetricsRead`.
   - Protected by session authentication (available to all logged-in members and admins).
4. **Web UI**:
   - `GET /` and `GET /dashboard` routes rendering `dashboard/index.html`.
   - Server cards displaying:
     - Display name and logical key.
     - Status badges: Up (green), Down (red), Stale (amber), Unreachable (gray), Disabled (neutral).
     - CPU utilization bar and percentage.
     - Memory utilization bar, percentage, and used/total GB.
     - Disk utilization bar, percentage, and used/total GB.
     - Near-term reservation summary (today's active plans from LabServer planning domain).
     - Deep-link button: "View Metrics in Beszel ↗".
   - Top navigation update in `base.html`: "Dashboard" and "Schedule" tabs with active indicator and user logout controls.
5. **Operations & Deployment**:
   - `services/core/src/labserver_core/seed_servers.py` / `ops/seed-servers.sh` to initialize the 4 standard lab servers (`fwq10`, `fwq51`, `fwq56`, `fwq57`).
   - Environment variables documented in `configs/examples/.env.production.example`.
   - Docker Compose and runbook updates.
   - End-to-end loopback smoke test verification.

### Explicit Non-Goals
- **No Telemetry Time-Series Storage in SQLite**: High-frequency metrics belong strictly in Beszel. LabServer does not persist metric history.
- **No Runtime Collector (psutil/nvitop)**: Per-process / per-user PID observation on hosts is Milestone M2-D.
- **No Public Caddy Reverse Proxy / Cloudflare Mounting**: Public exposure remains an isolated operational change after full M2 milestone validation.
- **No Job Scheduler or Workload Dispatch**: Planning remains published intent; observation remains read-only.

---

## 3. Architectural Seams & Contracts

```text
[ Browser / Web UI ]
       |
       |  GET /dashboard (Session Cookie)
       v
[ apps/web ]
       |
       |  GET /api/v1/monitoring/dashboard (Core HTTP Client)
       v
[ services/core ]
       |
       +---> [ ServerRepository ] (SQLite: ManagedServerModel)
       |
       +---> [ PlanRepository ] (SQLite: PlanEntryModel)
       |
       +---> [ HostMetricsProvider (Interface) ]
                   |
                   +---> [ FakeHostMetricsProvider ] (Tests / Offline)
                   |
                   +---> [ BeszelAdapter ] (Production Edge Adapter)
                               |
                               |  PocketBase REST API (HTTP + Token)
                               v
                     [ Beszel Hub (PocketBase) ]
                               |
                               |  WebSocket / Ingest
                               v
                     [ Beszel Agents on Hosts ]
```

### 3.1 Monitoring Contracts (`packages/contracts/src/labserver_contracts/monitoring.py`)

```python
class HostStatus(StrEnum):
    UP = "up"
    DOWN = "down"
    UNKNOWN = "unknown"

class FreshnessStatus(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    UNREACHABLE = "unreachable"
    DISABLED = "disabled"
    UNKNOWN = "unknown"

class GpuMetricsRead(ReadModel):
    index: int
    name: str | None = None
    utilization_percent: float | None = None
    memory_used_gb: float | None = None
    memory_total_gb: float | None = None
    temperature_c: int | None = None

class HostMetricsRead(ReadModel):
    server_key: str
    status: HostStatus
    freshness: FreshnessStatus
    cpu_percent: float | None = None
    memory_used_gb: float | None = None
    memory_total_gb: float | None = None
    memory_percent: float | None = None
    disk_used_gb: float | None = None
    disk_total_gb: float | None = None
    disk_percent: float | None = None
    load_average: tuple[float, float, float] | None = None
    uptime_seconds: int | None = None
    gpus: list[GpuMetricsRead] | None = None
    upstream_url: str | None = None
    updated_at: UtcDateTime | None = None
    error_message: str | None = None

class ServerDashboardCard(ReadModel):
    server: ServerRead
    metrics: HostMetricsRead | None = None
    active_plans_count: int = 0
    near_term_plans: list[PlanEntryRead] = []

class DashboardRead(ReadModel):
    cards: list[ServerDashboardCard]
    observed_at: UtcDateTime
```

### 3.2 Beszel Hub Protocol & Adapter Mapping

Beszel Hub runs on PocketBase.
- **Authentication**:
  - `POST {HUB_URL}/api/collections/_superusers/auth-with-password` (PocketBase >=0.23) or `POST {HUB_URL}/api/collections/users/auth-with-password` with `identity` (email/username) and `password`.
  - Or pre-configured `LABSERVER_BESZEL_TOKEN`.
  - Token is cached in memory.
- **System List**:
  - `GET {HUB_URL}/api/collections/systems/records?perPage=100` with `Authorization: Bearer {token}`.
  - Response payload:
    ```json
    {
      "items": [
        {
          "id": "9m348zi8mvs1rvb",
          "name": "vps76",
          "host": "117.72.218.76",
          "status": "up",
          "updated": "2026-09-18 04:04:44.394Z",
          "info": {
            "cpu": 4.13,
            "mp": 60.45,
            "dp": 76.02,
            "la": [1.57, 1.27, 1.38],
            "u": 7615621,
            "v": "0.18.7"
          }
        }
      ]
    }
    ```
- **Mapping Logic**:
  - System matching: `system.name.lower() == server_key.lower()` or matched via `LABSERVER_BESZEL_KEY_MAP`.
  - `cpu_percent = info.get("cpu")`
  - `memory_percent = info.get("mp")`
  - `memory_total_gb = server.memory_gb` (from capacity registry)
  - `memory_used_gb = round(server.memory_gb * memory_percent / 100, 1)` if `memory_total_gb` is known.
  - `disk_percent = info.get("dp")`
  - `load_average = tuple(info["la"][:3])` if `info.get("la")` else None.
  - `uptime_seconds = info.get("u")`
  - `updated_at = parse_iso(item["updated"])`
  - `freshness`:
    - If `item["status"] == "up"` and `now - updated_at <= freshness_threshold`: `FRESH`
    - If `item["status"] == "up"` and `now - updated_at > freshness_threshold`: `STALE`
    - If `item["status"] == "down"`: `UNREACHABLE`
    - If server is disabled in DB: `DISABLED`
  - `upstream_url`: `{LABSERVER_BESZEL_PUBLIC_URL}/system/{system.name}`.

---

## 4. Resilience & Error Budgets

1. **Host Isolation**: Failure to query Beszel or a failure on one monitored host must never degrade or block requests for other hosts.
2. **Timeouts**: Connect timeout: 3s; Read timeout: 5s. Total timeout per fetch: 5s.
3. **Caching**: In-memory cache with 15s TTL. Concurrent requests during cache expiry collapse onto a single refresh lock.
4. **Offline / Unreachable Behavior**: If Beszel Hub cannot be reached (e.g. ECONNREFUSED, timeout, 502), the adapter returns `HostMetricsRead(server_key=k, status=UNKNOWN, freshness=UNREACHABLE, error_message=...)`. The UI continues to display static server capacity, plan entries, and an unreachable badge without crashing.

---

## 5. Web UI Design

### 5.1 Dashboard Surface (`/` and `/dashboard`)
- **Header**:
  - LabServer brand logo.
  - Navigation: `[ Dashboard ]` | `[ Schedule ]`.
  - Viewer info: username, role badge, `[ Log out ]`.
- **Primary Grid**:
  - 4 Server Cards:
    - **Header**: Server Name (`fwq10`), Logical Key, Status Badge (Up / Down / Stale / Unreachable).
    - **Resource Gauges / Bars**:
      - CPU: percent + progress bar (green <70%, yellow 70-90%, red >90%).
      - Memory: percent + used/total GB + progress bar.
      - Disk: percent + used/total GB + progress bar.
      - Load average & uptime (subtle secondary text).
    - **Schedule Pressure**:
      - Count of active plans today.
      - Snippet of current ongoing plans (who, GPU allocation, remaining time).
    - **Actions**:
      - Direct deep-link: `[ Open in Beszel ↗ ]`
      - Quick link to server schedule: `[ View Schedule → ]`

---

## 6. Seeding the 4 Initial Lab Servers

To ensure standard operation immediately upon startup, `ops/seed-servers.sh` and Python bootstrap logic will register the four primary lab compute servers:
- `fwq10`: 48 cores, 256 GB RAM, 4 GPUs (logical key `fwq10`)
- `fwq51`: 48 cores, 256 GB RAM, 4 GPUs (logical key `fwq51`)
- `fwq56`: 64 cores, 512 GB RAM, 8 GPUs (logical key `fwq56`)
- `fwq57`: 64 cores, 512 GB RAM, 8 GPUs (logical key `fwq57`)

This data matches the actual fleet specs from the `vps-infra` knowledge base.

---

## 7. Verification Strategy

1. **Unit Tests (Core & Contracts)**:
   - Contract models validation, serialization, and deserialization.
   - Beszel adapter parsing of PocketBase response payloads.
   - Token lifecycle, caching, and refresh logic.
   - Freshness evaluation and timeout fallbacks.
   - Test double `FakeHostMetricsProvider` integration with `MonitoringService`.
2. **Core API Tests**:
   - `GET /api/v1/monitoring/dashboard`: test with authenticated member and admin sessions.
   - Unauthenticated access returns HTTP 401.
3. **Web Tests**:
   - `GET /` and `GET /dashboard`: test authenticated rendering, card metrics, warning badges, and navigation.
   - Unauthenticated access redirects to `/login`.
   - Core API failure handling (graceful error state).
4. **Remote Container Verification (`labenv.sh` on fwq10ys)**:
   - Locked dependency check: `uv sync --all-packages --dev --locked`.
   - Linter: `uv run ruff check .`.
   - Static type check: `uv run mypy services/core/src packages/contracts/src apps/web/src`.
   - Full test suite: `uv run pytest -q`.
5. **Real Docker Compose & Live Beszel Smoke Test on fwq10ys**:
   - Build image with Docker on `fwq10ys`.
   - Run seed script to seed the 4 servers.
   - Start Docker Compose stack with Beszel Hub configured (`http://127.0.0.1:27090` or `beszel:8090`).
   - Run automated loopback smoke script validating that `/dashboard` renders live data.
