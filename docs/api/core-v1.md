# Core API v1

Status: Milestone 1 interface baseline

LabServer Core v1 is the central planning API for users, logical servers, task requests, reservations, and advisory resource conflicts. It deliberately does **not** poll lab hosts, execute commands, submit jobs, or act as a scheduler.

## Boundary and transport

- Base prefix for product APIs: `/api/v1`.
- Health endpoint: `/healthz`.
- JSON request/response bodies use the schemas from `labserver_contracts`.
- Human authentication transport is not implemented in Milestone 1. Protected routes resolve a `CurrentActor` dependency that defaults to HTTP `401` until a trusted authentication adapter or test override supplies an actor.
- Agent authentication is a separate future concern and is not part of Core v1.
- All persisted timestamps are UTC-aware. API inputs that represent times must include timezone information.

No route accepts a private server IP as server identity. A managed server is identified by its stable logical ID/key; deployment-time endpoint mappings stay outside the database and outside this API.

## Error envelope

All application/domain errors are exposed through a stable machine-readable envelope:

```json
{
  "error": {
    "code": "invalid_transition",
    "message": "Request cannot transition from approved to submitted"
  }
}
```

Primary codes in M1:

| Code | Typical status | Meaning |
| --- | ---: | --- |
| `unauthorized` | 401 | No trusted actor was supplied. |
| `forbidden` | 403 | Authenticated actor lacks permission. |
| `not_found` | 404 | Requested entity does not exist or is not visible. |
| `invalid_transition` | 409 | Request lifecycle transition is not allowed. |
| `server_disabled` | 409 | A submitted request targets a disabled server. |
| `capacity_exceeded` | 409 | Declared resources exceed known server capacity. |
| `validation_error` | 422 | Contract/domain input is invalid. |
| `service_unavailable` | 503 | Core readiness dependency, currently the database, is unavailable. |

## Roles

M1 has two roles: `member` and `admin`.

| Capability | member | admin |
| --- | :---: | :---: |
| Read logical server registry | yes | yes |
| Create/update logical servers | no | yes |
| List users / create users | no | yes |
| Create own request | yes | yes |
| View own requests | yes | yes |
| View all requests | no | yes |
| Edit own draft | yes | yes, subject to service rules |
| Submit/cancel own request | yes | yes, subject to service rules |
| Approve/reject requests | no | yes |
| Preview request conflicts | owner only | yes |
| View reservations | yes | yes |

Authorization is enforced in the application service layer as well as at the HTTP dependency boundary. Routes do not create an alternate permission model.

## Health

### `GET /healthz`

Public readiness endpoint. It checks the Core process and database connection only.

It must not contact `fwq10`, `fwq51`, `fwq56`, `fwq57`, Beszel, a Lab Agent, or any other managed host. A single unavailable compute server therefore cannot make central Core unhealthy.

Success:

```json
{"status":"ok"}
```

Database readiness failure returns `503` with `service_unavailable`.

## Users

### `GET /api/v1/users`

Admin only. Returns all registered Core users.

### `POST /api/v1/users`

Admin only. Creates a user from the shared `UserCreate` contract.

M1 user identity is a planning/authorization identity. Linux username mapping belongs to the later observation/reconciliation milestone.

## Managed servers

### `GET /api/v1/servers`

Member/admin. Returns logical server records and declared capacities.

### `POST /api/v1/servers`

Admin only. Creates a logical server record.

Core fields represent stable identity and planning capacity, for example:

- logical `key` such as `fwq10`;
- display name;
- enabled state;
- optional CPU core capacity;
- optional memory capacity;
- optional GPU count.

Private IPs and runtime endpoints are intentionally not contract fields and are not persisted as server identity.

## Task requests

A `TaskRequest` represents a person's declared intent to use resources. It is not a running process and it is not a dispatched job.

### Lifecycle

```text
draft -> submitted -> approved
                    -> rejected

draft -> cancelled
submitted -> cancelled
```

Invalid backward/revival transitions are rejected. Approval is admin-only.

### `GET /api/v1/requests`

- Member: own requests only.
- Admin: all requests.

### `GET /api/v1/requests/{request_id}`

Owner or admin.

### `POST /api/v1/requests`

Creates a request owned by the current actor. M1 has no HTTP field that allows a member to select another owner.

Core request resource fields include:

- title and optional project/note;
- preferred logical server;
- planned start and duration;
- CPU cores;
- optional memory;
- GPU count;
- optional explicit GPU IDs.

### `PATCH /api/v1/requests/{request_id}`

Updates a draft request under application-service ownership rules. Submitted/approved/rejected/cancelled requests are not silently rewritten into new plans.

### `POST /api/v1/requests/{request_id}/submit`

Owner/admin under service rules. Submission validates that the target server is enabled and that the request does not exceed known server capacity unless an explicit admin override exists in the application service.

### `POST /api/v1/requests/{request_id}/cancel`

Owner/admin under service lifecycle rules.

### `POST /api/v1/requests/{request_id}/reject`

Admin only.

### `POST /api/v1/requests/{request_id}/approve`

Admin only. Approval is transactional and idempotent:

1. load and authorize the request;
2. validate `submitted -> approved`;
3. construct its reservation;
4. evaluate advisory conflicts;
5. persist request + reservation + audit event in one unit of work;
6. commit once.

`reservations.request_id` is unique. Repeating approval returns the already-created reservation rather than creating a duplicate.

## Advisory conflicts

### `GET /api/v1/requests/{request_id}/conflicts`

Owner/admin. Returns the current conflict preview for the request.

M1 conflict semantics are **advisory**. A conflict does not submit, queue, move, kill, block, or otherwise enforce a workload.

Scheduling uses half-open intervals `[start, end)`, so adjacent reservations do not overlap.

Conflict evaluation accounts for:

- aggregate CPU capacity;
- aggregate memory when capacity is known;
- aggregate GPU count;
- exact GPU-ID overlap when both assignments are explicit;
- `uncertain` placement warnings when explicit IDs overlap a count-only reservation and exact device placement cannot be known.

Conflict responses identify the affected resource, certainty, overlap segment, requested/available capacity, conflicting reservation IDs, and an explanatory reason.

## Reservations

A `Reservation` is an accepted plan. It is separate from the request that may have created it.

### `GET /api/v1/reservations?start=<time>&end=<time>&server_id=<uuid>`

Member/admin. Returns reservations overlapping the requested time window, optionally filtered to one logical server.

`start` and `end` must include timezone information and are normalized to UTC.

Reservation states in the domain include `planned`, `active`, `completed`, and `cancelled`; M1 does not infer runtime activity because there is no Lab Agent yet.

## Persistence and transaction boundary

- SQLite is the M1 database.
- Alembic owns schema migrations from the first schema.
- SQLite foreign keys are enabled on every connection.
- ORM rows are persistence-adapter details; repositories return domain entities.
- API route modules must not import SQLAlchemy or persistence models.
- Approval uses one unit of work so request/reservation/audit writes commit or roll back together.

## Explicit M1 non-capabilities

Core v1 does not:

- connect to managed-server private IPs;
- collect CPU, RAM, disk, GPU, process, or Linux-user observations;
- integrate with Beszel, `psutil`, `nvitop`, or NVML;
- expose remote shell or arbitrary command execution;
- start, kill, reprioritize, or migrate processes;
- submit Slurm-like jobs or implement a queue;
- stream SSE runtime state;
- reconcile observed processes against reservations;
- calculate final usage/accounting statistics;
- provide a browser UI.

Those capabilities, where in scope, are introduced behind the approved harness boundaries in later milestones.
