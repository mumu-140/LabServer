# LabServer Core v1 API

LabServer Core v1 is the shared planning API for users, logical servers, published plan entries, and advisory resource conflicts. It deliberately does **not** poll lab hosts, execute commands, submit jobs, or act as a scheduler.

Planning means only: "I intend to use this server/resource during this time window." Publishing a plan is never gated, never queued, and never dispatched. No plan state is held back for sign-off, no capacity is locked by a plan entry, and nothing is dispatched, placed, or enforced in v1.

## Base

- All endpoints live under `/api/v1`.
- JSON request/response bodies use the schemas from `labserver_contracts`.

## Error envelope

Every non-success response has the same shape:

```json
{ "error": { "code": "not_found", "message": "Plan ... does not exist" } }
```

| code | HTTP | Meaning |
| --- | --- | --- |
| `unauthorized` | 401 | Authentication transport is not configured (v1 is default-deny). |
| `forbidden` | 403 | Actor cannot touch someone else's plan or lacks admin privileges. |
| `not_found` | 404 | Requested entity does not exist or is not visible. |
| `server_disabled` | 409 | A plan targets a disabled server. |
| `validation_error` | 422 | Input validation failed (for example a non-positive interval). |

## Actors

| Action | Member | Admin |
| --- | --- | --- |
| View all published plans | yes | yes |
| Create own plan | yes | yes |
| Update own plan | yes | yes |
| Update any plan | no | yes |
| Cancel own plan | yes | yes |
| Cancel any plan | no | yes |
| List users / servers (planning metadata) | yes | yes |
| Manage users / servers | no | yes |

Human authentication transport is intentionally not implemented yet; production APIs stay `default deny` until it is. Tests use the standard FastAPI dependency override.

## Shared concepts

- Times are UTC-aware; inputs keep a timezone offset and are normalized to UTC.
- Time windows are half-open `[start_at, end_at)`. Adjacent entries (`10:00–12:00` then `12:00–14:00`) do not overlap.
- Optional quantities (`cpu_cores`, `memory_gb`, `gpu_count`, `gpu_ids`) mean *not declared*, never zero usage.
- `display_state` is derived from time only (`cancelled`, `upcoming`, `ongoing`, `past`) and is never persisted.

## Plan entries

A `PlanEntry` is a person's published intent to use a logical server during a window. It is not an allocation and not a lock: conflicts are advisory warnings that never block creating or updating a plan.

### `GET /api/v1/plans`

Lists published plans, optionally filtered by `server_id`, `owner_id`, `start`, `end` (half-open overlap: a plan counts when `plan.start_at < end` and `plan.end_at > start`), and `include_cancelled` (default `false`).

### `GET /api/v1/plans/{plan_id}`

Single plan view.

### `POST /api/v1/plans`

Publishes a plan owned by the current actor. Minimum fields: `server_id`, `title`, `start_at`, `end_at`; every resource field is optional intent. Overlap warnings are exposed via the conflicts endpoint and never block the call.

### `PATCH /api/v1/plans/{plan_id}`

Partial mutation of the mutable intent fields; members may edit only their own plans, admins may edit any plan. `owner_id` is never client-settable.

### `POST /api/v1/plans/{plan_id}/cancel`

Sets `cancelled_at` once. Repeated calls are idempotent and keep the first timestamp.

### `GET /api/v1/plans/{plan_id}/conflicts`

Advisory overlap warnings for one plan against other not-cancelled plans on the same server:

```json
{
  "resource": "gpu_device",
  "certainty": "confirmed",
  "start_at": "2026-09-18T01:00:00Z",
  "end_at": "2026-09-18T02:00:00Z",
  "requested": [0],
  "available": [],
  "conflicting_plan_ids": ["..."],
  "reason": "Explicit GPU device plan overlaps on device(s): 0"
}
```

Explicit GPU IDs compare against identical devices; count-only GPU intent checks aggregate capacity; mixing explicit IDs with count-only plans reports `certainty: "uncertain"` instead of guessing device placement. CPU/RAM conflicts only count explicitly declared quantities. Cancelling is purely presentational: it is ignored by conflict evaluation.

## Servers and users

`GET /api/v1/servers`, `POST /api/v1/servers`: admin-managed logical server registry with optional capacity declarations (`cpu_cores`, `memory_gb`, `gpu_count`). Real hosts and IPs are never part of the API surface.

`GET /api/v1/users` is readable by any authenticated actor (member or admin): the planning user directory powers schedule owner filters and display names. `POST /api/v1/users` stays admin-only. The registry stores logical users (`admin`/`member`), used for ownership and display names.
