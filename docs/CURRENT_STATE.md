# Current State

Last updated: 2026-09-15

## Status

M1.1 implemented on branch `feat/m1-1-simple-planning`: `PlanEntry` + `/api/v1/plans` + `/schedule` are in place, and the old request/approval/reservation product slice has been removed. Not deployed.

## M1.1 scope delivered

- One public planning concept: `PlanEntry` ("I intend to use this server/resource during this time window"). No submission, sign-off, queue, priority, dispatch, or enforcement.
- Contracts: `PlanCreate`/`PlanUpdate`/`PlanRead`/`PlanDisplayState`/`PlanConflictRead` in `labserver_contracts.plans`.
- Core: domain `PlanEntry`, advisory conflict engine (`evaluate_plan_conflicts`), `PlanService` with member/admin ownership rules, idempotent cancel.
- Persistence: `0002_simple_planning` migration — `plan_entries` created, M1 development reservation data migrated (reservation UUID reused, cancelled → `cancelled_at`), legacy `task_requests`/`reservations` dropped.
- API: `GET/POST /api/v1/plans`, `GET/PATCH /api/v1/plans/{id}`, `POST /api/v1/plans/{id}/cancel`, `GET /api/v1/plans/{id}/conflicts` with schedule filters.
- Web: first harness `apps/web` — FastAPI + Jinja2 + vendored HTMX 2.0.4 + plain CSS; `/schedule` reads Core over HTTP via `CoreClient`; no conflict logic, no database access.
- Guards: architecture boundary tests extended with a terminology guard over active sources and `docs/api`.

## Removed

The M1 public slice `TaskRequest -> submit -> approve/reject -> Reservation` is deleted end to end (contracts, domain, application, persistence, API, tests). `TaskRequest`, `Reservation`, `TaskRequestStatus`, `ReservationStatus`, and `ReservationSource` are no longer part of the planning API.

## Boundaries

- web -> HTTP/contracts -> core; core -> application ports -> persistence. Routes never touch SQLAlchemy.
- Human authentication transport is not yet implemented; protected routes remain default-deny until an explicit trusted adapter is selected. No production auth bypass exists.

## Next gate

1. Review + CI on the final `feat/m1-1-simple-planning` head; merge only when green.
2. Then finalize the M2 Docker + Beszel + Runtime Collector design and implementation plan.
