# Harness Architecture

LabServer uses explicit harness boundaries so agents and maintainers can work on one concern without loading or modifying the whole system.

## Harness map

```text
apps/
  web/                  # UI composition and browser-facing routes
services/
  core/                 # domain/application service
  agent/                # host observation service
packages/
  contracts/            # stable DTOs / API schemas shared across boundaries
  testkit/              # shared fixtures only, no business logic
ops/                     # deployment/runtime assets
configs/
  examples/              # safe templates only

docs/
  harnesses/
    web.md
    core.md
    agent.md
    ops.md
  adr/
  api/
  operations/
  superpowers/specs/
  superpowers/plans/
```

Directories may be introduced incrementally during implementation, but ownership and dependency direction are fixed by this document.

## Dependency direction

```text
web  ---> contracts <--- core <--- persistence adapters
          ^               ^
          |               |
        agent --------> ingestion adapter

ops configures/runs components but contains no domain logic.
```

Rules:

1. `web` consumes core HTTP/API contracts; it does not import core persistence or monitoring internals.
2. `agent` emits observation DTOs defined by `contracts`; it does not know about task requests or reservations.
3. `core` owns business rules and maps observations into domain concepts such as runtime activity and plan reconciliation.
4. External systems (Beszel, nvitop, psutil) are adapters at the edge.
5. `contracts` contains schemas and shared enums only. No service logic, database access, or UI code.
6. `ops` may reference component names and configuration keys, never Python/JS internals.

## Harness: web

Owns:
- Dashboard and server cards.
- Running-activity views.
- Request/plan forms.
- Schedule/calendar views.
- Statistics presentation.
- Client-side polling/SSE consumption.

Does not own:
- Conflict rules.
- Approval state transitions.
- Resource accounting.
- Observation normalization.

## Harness: core

Owns:
- Users and roles.
- Managed-server registry by logical name + runtime IP mapping reference.
- Task requests.
- Reservations/plans.
- Conflict evaluation.
- Observed runtime activities.
- Plan-vs-actual reconciliation.
- Usage aggregation.
- API authorization and domain validation.

Core must be testable without Beszel or a physical GPU.

## Harness: agent

Owns only read-only observation on one managed server:
- host identity and heartbeat;
- CPU/memory/load/storage observations where required;
- process ownership and runtime metadata via `psutil`;
- NVIDIA GPU/device/process observations via `nvitop`/NVML;
- bounded, authenticated delivery to core or pull endpoint.

Agent explicitly does not:
- execute commands supplied by central server;
- kill/reprioritize processes;
- submit jobs;
- expose arbitrary filesystem content;
- return full command lines by default.

## Harness: ops

Owns:
- Docker/systemd/service definitions;
- environment templates;
- reverse proxy/TLS if used;
- backup/restore procedures;
- upgrades and rollback;
- health-check runbooks.

Production values live outside Git. Repository files contain placeholders and safe examples only.

## Cross-harness change protocol

A change is considered cross-harness if it modifies any of:
- DTO/API schema;
- authentication model;
- server identity model;
- task/request/reservation lifecycle;
- observation payload;
- data ownership;
- deployment topology.

Such changes require:
1. an ADR under `docs/adr/`;
2. contract tests;
3. updates to each affected harness guide;
4. explicit compatibility/migration notes.

## Harness-local rules

Each harness guide under `docs/harnesses/` should contain only daily maintenance guidance: local entrypoints, permitted dependencies, tests, invariants, and common failure modes. Long architecture explanations belong here or in ADRs, not in harness files.
