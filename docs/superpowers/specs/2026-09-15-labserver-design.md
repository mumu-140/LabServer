# LabServer Initial Architecture Design

Date: 2026-09-15
Status: Approved

## 1. Problem statement

The lab needs a small, low-maintenance system to coordinate a handful of Linux compute servers (`fwq10`, `fwq51`, `fwq56`, `fwq57`) on a private network. Today the useful questions are operational rather than HPC-scheduler questions:

- Which servers are online and how busy are CPU, memory, storage, and GPU resources?
- Which users/processes are consuming resources right now?
- What work does each person plan to run, when, and with how many resources?
- Are future plans likely to conflict?
- Does observed activity correspond to a declared plan?
- How much CPU/GPU time is planned or consumed over useful reporting windows?

The system should answer these questions without introducing a full scheduler or a large observability stack.

## 2. Product boundary

### In scope for V1

- Register a small fixed set of managed servers by logical name and deployment-time private IP.
- Read server health and host-level resource metrics.
- Read current Linux process ownership and GPU-process occupancy.
- Show current activity by server, user, process, GPU, elapsed time, CPU, memory, and GPU memory where available.
- Create and edit human-entered task/resource requests.
- Approve or auto-approve requests into reservations/plans.
- Detect overlapping resource plans and present warnings.
- Present a server/GPU schedule timeline.
- Reconcile observed runtime activity with declared reservations.
- Report simple CPU-core-hours, GPU-hours, reservation utilization, and availability summaries.
- Provide basic admin/member authorization.

### Explicit non-goals

- No batch queue.
- No automatic workload placement.
- No SSH/remote shell.
- No process kill/reprioritization.
- No package/environment management.
- No Kubernetes/container orchestration.
- No billing/chargeback.
- No full replacement for Beszel or another monitoring backend.

The non-goals are architectural constraints, not merely deferred UI features.

## 3. Architectural approach

LabServer is a thin coordination layer around mature telemetry sources.

```text
Managed host                    Central LabServer
+----------------------+        +-----------------------------------+
| Beszel Agent         |------->| Beszel Hub / host metric adapter  |
|                      |        |                                   |
| Lab Agent            |------->| Observation ingestion             |
|  - psutil            |        |       |                           |
|  - nvitop/NVML       |        |       v                           |
+----------------------+        | Core domain/application service   |
                                |  - requests                        |
                                |  - reservations                    |
                                |  - conflicts                       |
                                |  - reconciliation                  |
                                |  - usage summaries                 |
                                |       |                           |
                                |       v                           |
                                | SQLite                            |
                                |       |                           |
                                |       v                           |
                                | Web UI / SSE                      |
                                +-----------------------------------+
```

Beszel remains responsible for host-level monitoring/history/alerts. Lab Agent exists only to fill the process/user/GPU-process gap required by lab coordination.

## 4. Harness decomposition

The repository is divided into four independently understandable harnesses plus shared contracts.

```text
LabServer/
├── AGENTS.md
├── README.md
├── apps/
│   └── web/
├── services/
│   ├── core/
│   └── agent/
├── packages/
│   ├── contracts/
│   └── testkit/
├── ops/
├── configs/
│   └── examples/
├── docs/
│   ├── PROJECT_KNOWLEDGE.md
│   ├── CURRENT_STATE.md
│   ├── HARNESS_ARCHITECTURE.md
│   ├── harnesses/
│   │   ├── web.md
│   │   ├── core.md
│   │   ├── agent.md
│   │   └── ops.md
│   ├── adr/
│   ├── api/
│   ├── operations/
│   └── superpowers/
│       ├── specs/
│       └── plans/
└── tests/
    └── contract/
```

The exact implementation language/tooling layout inside a harness can evolve, but cross-harness ownership and dependency direction are stable.

### web harness

Responsibility: browser-facing presentation and interaction only.

Owns dashboards, forms, schedules, filtering, navigation, progressive enhancement, and real-time rendering. It consumes APIs/contracts from core. It must never implement conflict detection, approval state transitions, accounting logic, or telemetry normalization.

### core harness

Responsibility: product/business truth.

Owns users/roles, managed-server registry, request lifecycle, reservations, conflict evaluation, observed activities, reconciliation, reporting, authorization, persistence boundaries, and API behavior.

Core must run and be testable without access to a physical server, Beszel, or NVIDIA GPU.

### agent harness

Responsibility: bounded read-only observation of one host.

Owns local collection and normalization of process/GPU observations. The agent knows nothing about requests or reservations. It emits observation contracts and has no generic command-execution endpoint.

### ops harness

Responsibility: reproducible deployment and operation.

Owns service definitions, environment templates, health checks, upgrades, rollback, backup/restore, and runbooks. It contains no domain decisions.

## 5. External component strategy

### Beszel

Use Beszel as the preferred host-level monitoring source rather than reproducing time-series monitoring. LabServer should consume only the subset it needs for current dashboard state and deep-link to upstream history where appropriate.

The adapter must make the rest of LabServer unaware of Beszel-specific collection/storage types. A future monitoring source should be replaceable behind the same core-facing interface.

### psutil

Use `psutil` for stable process/system observation such as PID, username, CPU usage, memory usage, process start time, and safe process names. Handle access-denied and disappearing-process races as normal conditions.

### nvitop / NVML

Use `nvitop`/NVML APIs for NVIDIA GPU device and process observations. Do not scrape human-oriented `nvidia-smi` output.

GPU visibility is best effort: missing driver/NVML capability must produce a clear `unsupported` or `unavailable` state rather than breaking host observation.

## 6. Server identity and private-network configuration

A managed server has two distinct identities:

1. stable logical identity stored in the database, e.g. `fwq10`;
2. deployment endpoint/private IP supplied by runtime configuration.

Do not use IP address as a database primary key. IPs may change; task/reservation history must continue to refer to the stable server identity.

Suggested model:

```text
ManagedServer
- id: UUID
- key: string unique          # fwq10
- display_name: string
- enabled: bool
- capabilities: JSON/typed fields
- created_at
- updated_at
```

Runtime connection data is injected from environment/configuration and mapped by `key`:

```text
LABSERVER_HOST_FWQ10=http://<private-ip>:<port>
```

Repository examples contain placeholders only.

## 7. Domain model

### User

```text
User
- id
- username
- display_name
- role: admin | member
- enabled
```

User identity used for planning should be explicitly mapped to observed Linux usernames where necessary rather than assuming they always match.

### TaskRequest

Represents intent to use resources.

```text
TaskRequest
- id
- title
- requester_id
- project
- preferred_server_id
- planned_start
- planned_duration_minutes
- requested_cpu_cores
- requested_memory_gb nullable
- requested_gpu_count
- preferred_gpu_ids nullable
- note nullable
- status: draft | submitted | approved | rejected | cancelled
- created_at
- updated_at
```

Validation rules:
- duration > 0;
- CPU cores >= 0;
- GPU count >= 0;
- preferred GPU IDs, if present, must be unique;
- the selected server must be enabled when submitted;
- no request may claim more known resources than a server capability unless an admin explicitly records an exception.

### Reservation

Represents an accepted resource plan.

```text
Reservation
- id
- request_id nullable
- owner_id
- server_id
- title
- start_at
- end_at
- cpu_cores
- memory_gb nullable
- gpu_count
- gpu_ids nullable
- status: planned | active | completed | cancelled
- source: request | admin
- created_at
- updated_at
```

Reservation is separate from TaskRequest so admin-created plans and future request-policy changes do not distort historical requests.

### ObservedActivity

Represents normalized current runtime state, primarily ephemeral.

```text
ObservedActivity
- observation_id
- server_id
- observed_at
- linux_username
- pid
- process_name
- process_started_at nullable
- cpu_percent nullable
- memory_bytes nullable
- gpu_devices[]
- gpu_memory_bytes nullable
```

Full command line is intentionally absent from the normal contract.

### ReconciliationResult

Derived, explainable state connecting observations and reservations.

Possible classifications:
- `planned_running`
- `planned_not_observed`
- `unplanned_activity`
- `overrun`
- `ambiguous`

A reconciliation result stores/returns reasons and confidence; it never silently changes the reservation.

## 8. Request and plan workflow

Default workflow:

```text
draft -> submitted -> approved -> reservation(planned)
                    \-> rejected

draft/submitted -> cancelled
```

Configuration may enable auto-approval:

```text
submitted -> approved -> reservation(planned)
```

Approval creates a reservation in one transaction. Repeated approval must be idempotent and must not create duplicate reservations.

Reservation time state can be derived/maintained as:
- `planned`: before start or not yet observed;
- `active`: within/after start and associated activity exists, or admin marks active;
- `completed`: explicitly completed or reconciled after end under defined policy;
- `cancelled`.

Avoid over-automation in V1. Runtime observations inform state but do not rewrite the user’s declared start/end times.

## 9. Conflict detection

Conflict detection is advisory in V1.

Two reservations potentially conflict when:

```text
same server
AND time intervals overlap
AND any constrained resource is oversubscribed
```

Interval overlap uses half-open intervals `[start, end)` so adjacent reservations do not conflict.

For explicit GPU IDs, detect exact device overlap. For GPU-count-only reservations, compute aggregate GPU capacity over the overlapping window and report uncertainty where device assignment is not explicit.

CPU/memory conflicts use aggregate requested capacity against known server capacity. A conflict result must identify:
- conflicting reservation(s);
- overlapping interval;
- constrained resource;
- requested vs available capacity.

The UI presents warnings; V1 does not block submission/approval solely due to conflict unless an admin policy later enables enforcement.

## 10. Reconciliation strategy

Automatic matching should use deterministic evidence first:

1. server identity;
2. mapped user/Linux username;
3. reservation time window plus configured grace period;
4. overlapping GPU IDs when specified;
5. resource shape as supporting evidence.

Do not match based on process name alone.

If multiple reservations are equally plausible, return `ambiguous` rather than inventing certainty.

Unplanned activity is a useful observation, not necessarily a violation. V1 should avoid punitive language.

## 11. Data collection and freshness

Agent observations should be low frequency and bounded. Initial target: 10-30 second collection cadence, configurable per deployment.

Every observation carries `observed_at` and server identity. Core/UI classify freshness, for example:
- fresh;
- stale;
- unavailable.

Exact thresholds belong in configuration, not hard-coded UI text.

One host failure must not affect other hosts. Network calls require connect/read timeouts and bounded retries with jitter/backoff where appropriate.

High-frequency raw telemetry should not be persisted by LabServer. Beszel owns detailed monitoring history. LabServer persists only the aggregates/audit records required for its own product semantics.

## 12. Reporting

V1 reporting should stay explainable and derived from reservations plus sampled/reconciled activity.

Initial metrics:
- planned GPU-hours;
- observed/reconciled GPU-hours where reliable;
- CPU-core-hours;
- reservation utilization by server;
- per-user usage summary;
- future available GPU windows.

Reports must state whether values are planned, observed, or estimated. Do not mix these into a single number without labeling provenance.

## 13. UI information architecture

### Dashboard

Four primary server cards (initially fwq10/51/56/57), showing online/freshness, CPU, memory, storage, GPU summary, current users, and near-term reservation pressure.

### Servers

Per-server resource detail and current activity. Detailed historical host telemetry may deep-link to Beszel rather than duplicating all charts.

### Running

Cross-server table grouped/filterable by user, server, GPU, process name, and elapsed time. Ordinary members do not see full command lines.

### Requests

Create/edit/submit own requests; admins approve/reject. Conflict preview is shown before approval.

### Schedule

Primary coordination surface: timeline by server/GPU with reservations, conflicts, and free windows.

### Statistics

Simple time-window summaries with provenance labels (`planned`, `observed`, `estimated`).

## 14. API and real-time behavior

Use ordinary HTTP APIs for CRUD/query operations.

Use SSE for server-side push of current dashboard/activity snapshots unless implementation evidence shows WebSocket is necessary. SSE is sufficient for one-way state updates and reduces connection/state complexity.

Contracts must be versionable and live in `packages/contracts` (or generated equivalents). Core API errors should have stable machine-readable codes plus user-readable messages.

## 15. Persistence and migrations

SQLite is the V1 database.

Rules:
- migrations are mandatory from the first schema;
- SQLite foreign keys enabled;
- timestamps stored in UTC, rendered in user/deployment timezone;
- task/request/reservation changes that matter to audit should preserve timestamps and actor identity;
- no telemetry firehose into SQLite.

Do not introduce PostgreSQL until measured concurrency/operational needs justify it.

## 16. Authentication and authorization

Because the system is internal does not mean authorization can be omitted.

V1 requires authenticated users and two roles:
- member;
- admin.

Minimum policy:
- members can view shared server/schedule state;
- members can create and manage their own requests within lifecycle rules;
- admins can manage servers, users, approvals, and reservations;
- agent authentication is separate from human sessions.

The precise human login mechanism may be selected during implementation planning based on the lab environment, but authorization boundaries above are fixed.

## 17. Privacy and security

- Never commit real infrastructure endpoints or credentials.
- Agent returns process name, PID, resource use, and username mapping only; full arguments are excluded by default.
- Treat arbitrary command execution as forbidden.
- Validate all externally supplied IDs/enums/resource quantities.
- Agent/core communication uses authentication and private-network transport; HTTPS or trusted reverse-proxy transport is preferred where practical.
- Logs must not contain tokens or raw secrets.
- Access to host/process metadata should be limited to what Linux permissions naturally expose; do not escalate privileges merely to collect more detail without a specific design review.

## 18. Error model

Operational failure is normal and must be represented explicitly.

Examples:
- server unreachable;
- Beszel unavailable;
- GPU unsupported;
- process disappeared during sampling;
- permission denied reading process detail;
- stale observation;
- partial host snapshot.

UI should show partial truth rather than converting partial failures into an all-red system failure.

## 19. Testing strategy

Testing follows the harness boundaries.

- `core`: unit tests for request lifecycle, conflict calculations, reconciliation, permissions, and accounting.
- `agent`: fixtures/fakes for psutil/nvitop adapters; tests for disappearing processes, access denied, no GPU, multiple GPU processes, and bounded payloads.
- `web`: route/view tests and a small set of critical browser interaction tests.
- `contracts`: schema compatibility and serialization tests.
- cross-harness: contract tests using fake agents/monitor adapters; no physical GPU required in CI.
- ops: configuration validation and health-check smoke tests where feasible.

CI must not require access to the lab private network.

## 20. Documentation architecture

Documentation is separated by lifespan and audience:

- `README.md`: project entrypoint and product overview.
- `AGENTS.md`: short global rules + routing only.
- `docs/PROJECT_KNOWLEDGE.md`: durable facts/decisions.
- `docs/CURRENT_STATE.md`: current milestone/state/next gate.
- `docs/HARNESS_ARCHITECTURE.md`: dependency/ownership map.
- `docs/harnesses/*.md`: daily development guidance for one harness.
- `docs/adr/*.md`: consequential architecture decisions.
- `docs/api/`: API/contracts once implemented.
- `docs/operations/`: deployment, backup, upgrades, incidents.
- `docs/superpowers/specs/`: validated designs.
- `docs/superpowers/plans/`: implementation plans.

Do not duplicate the same rule across several documents. Global invariant -> `AGENTS.md`; architectural rationale -> spec/ADR; harness-local routine -> harness guide.

## 21. Delivery sequence

Implementation should be sliced vertically rather than building all infrastructure first.

Recommended milestones:

1. **Foundation + core planning** — project skeleton, contracts, SQLite migrations, users/servers, request/reservation lifecycle, conflict engine, API tests.
2. **Read-only Lab Agent + Running view** — psutil/nvitop observation contract, ingestion, fake-agent integration, current activity UI.
3. **Dashboard + Beszel adapter** — host summary adapter and four-server dashboard with failure/freshness states.
4. **Schedule + reconciliation** — timeline, matching, unplanned/overrun states.
5. **Statistics + operations** — aggregates, deployment assets, backup/restore, upgrade runbook, production hardening.

Each milestone must produce usable/testable behavior and must not require later milestones to make its tests meaningful.

## 22. Decisions intentionally deferred to implementation planning

These are implementation choices, not missing product requirements:

- exact Python web framework/template package versions;
- exact human authentication mechanism;
- Beszel deployment topology (embedded alongside central service vs separately managed Hub);
- exact SSE library/implementation;
- chart/calendar UI library selection;
- packaging/container choice for each component.

Selection should optimize for maintainability, mature upstream support, and minimal operational burden while preserving the harness contracts in this spec.

## 23. Acceptance criteria for the architecture

The design is successful if:

- one unavailable host cannot take down the system;
- a developer can test core planning without any servers/GPUs;
- Beszel can be replaced without rewriting planning/business rules;
- Lab Agent can evolve without learning request/reservation semantics;
- UI can be redesigned without changing conflict/reconciliation rules;
- real IPs/secrets remain outside Git;
- the system stays understandable for a four-server lab and does not become a scheduler by accident.
