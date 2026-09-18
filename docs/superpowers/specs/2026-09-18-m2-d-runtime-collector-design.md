# M2-D: Minimal Read-Only Runtime Collector & "Running" View Design

Date: 2026-09-18  
Status: Proposed  
Branch: feat/m2-d-runtime-collector  
Target baseline: main (commit 43490c4, M2-C merged)

## 1. Context & Motivation

With M2-C (Beszel primary monitoring integration & Web host dashboard) successfully merged into `main`, LabServer displays aggregate host metrics (CPU, Memory, Disk, Status, Load, Uptime) for the lab's primary servers (`fwq10`, `fwq51`, `fwq56`, `fwq57`).

However, host-level telemetry alone cannot answer the critical operational questions of a shared compute cluster:
- **Which processes are currently occupying the GPUs?** (PID, command name, memory consumed).
- **Who owns those processes?** (OS username attribution, e.g. `tianzy` or `yangs`).
- **How does actual runtime utilization correlate with published intent?**
  - Is an active GPU workload running under an approved/scheduled plan (`MATCHED`)?
  - Is someone using GPU compute without an active plan (`UNPLANNED`)?
  - Is a GPU reserved by an active plan but currently completely idle (`IDLE_RESERVATION`)?

As specified in the foundational architecture ADRs and specs (`docs/adr/0001-simple-planning-model.md`, `docs/superpowers/specs/2026-09-15-labserver-design.md` §5.1, §11):
- LabServer coordinates intent and observation; **it is not a workload scheduler or process supervisor**.
- The Runtime Collector is **strictly read-only**: it never kills, stops, pauses, renices, or modifies any process.
- Attribution is informative and transparent, fostering collaborative hygiene rather than mechanical enforcement.
- Core must remain testable and deployable without GPUs, without root privileges, and without SSH credentials inside the container.

---

## 2. Scope & Boundaries

### In Scope
1. **Generic Runtime Contracts (`packages/contracts/src/labserver_contracts/runtime.py`)**:
   - `GpuProcessInfo`: Snapshot of a compute process running on a GPU (`gpu_id`, `pid`, `process_name`, `username`, `used_memory_mb`, `correlation`, `matched_plan_id`, `matched_plan_title`, `matched_plan_owner`).
   - `GpuDeviceRuntime`: Per-GPU hardware and operational metrics (`index`, `name`, `memory_total_mb`, `memory_used_mb`, `utilization_gpu_percent`, `temperature_celsius`, `processes`, `active_plans`).
   - `HostRuntimeReport`: Payload sent by the host collector (`server_key`, `reported_at`, `gpus`).
   - `HostRuntimeRead`: Normalized per-host runtime view (`server_key`, `display_name`, `status`, `reported_at`, `freshness`, `gpus`, `ongoing_plans`, `unplanned_processes_count`).
   - `RuntimeOverviewRead`: Aggregated runtime state across all managed servers for the Web UI.
   - Enums:
     - `RuntimeStatus`: `ACTIVE`, `IDLE`, `UNAVAILABLE`.
     - `RuntimePlanCorrelation`: `MATCHED`, `UNPLANNED`, `IDLE_RESERVATION`.

2. **Core In-Memory Runtime Store & Service (`services/core`)**:
   - `RuntimeStore`: Thread-safe in-memory store for the latest host runtime snapshots with TTL freshness evaluation (default: 120s threshold).
   - Ingress endpoint: `POST /api/v1/runtime/report` protected by shared collector bearer token (`LABSERVER_COLLECTOR_TOKEN`).
   - Correlation logic: `RuntimeService` cross-references active `ONGOING` plans from `PlanRepository` for `(server_id, now)` against reported GPU processes and device IDs:
     - If `process.username == plan_owner.username`: marked as `MATCHED` with linked plan details.
     - If process has no matching plan or user mismatch: marked as `UNPLANNED`.
     - If plan is active on a GPU with 0 compute processes: marked on device as `IDLE_RESERVATION`.
   - Read API:
     - `GET /api/v1/runtime/overview`: Requires user session.
     - `GET /api/v1/runtime/servers/{server_key}`: Requires user session.

3. **Lightweight Host Collector (`ops/labserver-collector.py`)**:
   - Zero external pip dependencies: Pure Python 3 standard library (`subprocess`, `urllib.request`, `json`, `argparse`, `sys`).
   - Runs on target hosts (via cron, systemd timer, or manual trigger).
   - Queries `nvidia-smi` for GPU devices and compute processes; resolves process ownership usernames via standard `ps`.
   - Gracefully handles non-GPU hosts (`fwq10`, `fwq56`): reports 0 GPUs without failure.
   - HTTP POST with retry/timeout to Core `POST /api/v1/runtime/report`.

4. **Web UI "Running" View (`apps/web`)**:
   - Navigation: Add "Running" tab in `base.html` header (`Dashboard` | `Running` | `Schedule`).
   - Route: `GET /running` with unauthenticated default-deny (redirect to `/login?next=/running`).
   - View template `running/index.html`:
     - Server selector / tabs or multi-server cards.
     - Per-GPU device status cards (GPU index, model, memory gauge, utilization, temperature).
     - Running GPU Process Table:
       - Columns: Host, GPU Device, PID, Command, User, GPU Memory, Booking Status badge (`● Matched`, `▲ Unplanned`, `○ Idle reservation`).
     - Empty states when no compute jobs are running.

5. **Ops & Smoke Verification (`ops/`)**:
   - Collector script: `ops/labserver-collector.py`.
   - Configuration: `LABSERVER_COLLECTOR_TOKEN` in `.env.production.example`.
   - Smoke test: update `ops/smoke-loopback.sh` with collector ingest and `/running` web page checks.

### Explicit Non-Goals
- **No Process Management or Killing**: Zero process termination or priority adjustment capabilities.
- **No In-Container SSH/Privilege Escalation**: Core never initiates outbound SSH connections to target hosts.
- **No Historical Telemetry Database**: Runtime state is ephemeral in-memory; historical metrics remain with Beszel.
- **No Mandatory Host Dependencies**: Core functions normally if no collector reports are received.

---

## 3. Architecture & Data Flow

```text
[ Target Host (e.g., fwq57 / fwq51) ]
       |
       |  nvidia-smi (GPU + processes) + ps (users)
       v
[ ops/labserver-collector.py ]
       |
       |  POST /api/v1/runtime/report (Header: Authorization: Bearer <COLLECTOR_TOKEN>)
       v
[ LabServer Core (services/core) ]
       |
       +---> [ RuntimeStore ] (In-memory latest snapshots + TTL)
       |
       +---> [ PlanRepository ] (SQLite: PlanEntryModel for ONGOING plans)
       |
       +---> [ RuntimeService ] (Correlation Engine: Matched vs Unplanned)
       |
       +---> GET /api/v1/runtime/overview (Session Auth)
       v
[ LabServer Web (apps/web) ]
       |
       |  GET /running (Session Cookie)
       v
[ Browser / Lab Member ]
```

---

## 4. Contract Specifications (`packages/contracts/src/labserver_contracts/runtime.py`)

```python
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from labserver_contracts.monitoring import FreshnessStatus
from labserver_contracts.plans import PlanRead


class RuntimeStatus(StrEnum):
    ACTIVE = "active"
    IDLE = "idle"
    UNAVAILABLE = "unavailable"


class RuntimePlanCorrelation(StrEnum):
    MATCHED = "matched"
    UNPLANNED = "unplanned"
    IDLE_RESERVATION = "idle_reservation"


@dataclass(frozen=True, slots=True)
class GpuProcessInfo:
    gpu_id: int
    pid: int
    process_name: str
    username: str
    used_memory_mb: float | None = None
    correlation: RuntimePlanCorrelation = RuntimePlanCorrelation.UNPLANNED
    matched_plan_id: UUID | None = None
    matched_plan_title: str | None = None
    matched_plan_owner: str | None = None


@dataclass(frozen=True, slots=True)
class GpuDeviceRuntime:
    index: int
    name: str
    memory_total_mb: float
    memory_used_mb: float
    utilization_gpu_percent: float | None = None
    temperature_celsius: float | None = None
    processes: tuple[GpuProcessInfo, ...] = ()
    active_plans_count: int = 0


@dataclass(frozen=True, slots=True)
class HostRuntimeReport:
    server_key: str
    reported_at: datetime
    gpus: tuple[GpuDeviceRuntime, ...] = ()


@dataclass(frozen=True, slots=True)
class HostRuntimeRead:
    server_key: str
    display_name: str
    status: RuntimeStatus
    reported_at: datetime | None
    freshness: FreshnessStatus
    gpus: tuple[GpuDeviceRuntime, ...]
    ongoing_plans: tuple[PlanRead, ...]
    unplanned_processes_count: int


@dataclass(frozen=True, slots=True)
class RuntimeOverviewRead:
    servers: tuple[HostRuntimeRead, ...]
    observed_at: datetime
```

---

## 5. Security & Authentication Model

1. **Ingress Token Authentication**:
   - `POST /api/v1/runtime/report` requires `Authorization: Bearer <token>` or `X-Collector-Token: <token>`.
   - Token is configured via `LABSERVER_COLLECTOR_TOKEN`.
   - If `LABSERVER_COLLECTOR_TOKEN` is unset or blank in production, collector ingress is disabled (returns 403 Forbidden).
   - In development/test mode, if token is unset, loopback reports are accepted.
2. **Web & API Viewer Authentication**:
   - `GET /running` and `GET /api/v1/runtime/*` require active member/admin session. Anonymous requests receive 401.

---

## 6. Implementation Strategy

1. **Task 1: Runtime Contracts & Tests**: Define DTOs, Enums, and serialization/contract unit tests in `packages/contracts`.
2. **Task 2: Core In-Memory Runtime Store & Correlation Service**: Implement `RuntimeStore`, `RuntimeService` with plan correlation, and unit tests.
3. **Task 3: Core Runtime API Endpoints**: Expose report ingress and read endpoints with tests.
4. **Task 4: Zero-Dependency Host Collector Script**: Implement `ops/labserver-collector.py` with mockable command execution.
5. **Task 5: Web Client & "Running" Route/UI**: Add CoreClient methods, `/running` route, navbar link, and responsive template with process table and badges.
6. **Task 6: Ops Integration & Loopback Verification**: Extend `ops/docker-compose.yml`, `.env.production.example`, and `ops/smoke-loopback.sh`.
7. **Task 7: CI Verification, PR & Merge**.
