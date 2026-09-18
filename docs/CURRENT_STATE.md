# Current State

Last updated: 2026-09-16

## Status

M1.1 simple planning and M1.1H web hardening are merged and verified on `main`. Neither is deployed.

M2-A production auth adapter design is proposed (`docs/superpowers/specs/2026-09-16-m2-auth-adapter-design.md`) and awaiting approval. Nothing else in M2 has started.

## Main baseline

M1.1H was squash-merged through PR #5:

- main commit: `3e7eacc3e5850e5c10a679fbe3c15d55189788fd`;
- merged-main CI run: `35079558365` (success);
- locked `uv sync`: success;
- Ruff: success;
- mypy across Core + contracts + Web: success (42 files);
- pytest: `141 passed`;
- no production deployment has occurred.

M1.1 itself was squash-merged through PR #4 (main commit `a2ce4a924cb017c3730fa393dc9f78d6fb882407`, merged-main CI run `35036877089`, `97 passed` at that point).

## M1.1 delivered

- One public planning concept: `PlanEntry` ("I intend to use this server/resource during this time window").
- No submission, approval/rejection, queue, priority, dispatch, resource lock, or enforcement.
- `PlanCreate` / `PlanUpdate` / `PlanRead` / `PlanDisplayState` / `PlanConflictRead` contracts.
- `PlanEntry` domain, advisory conflict engine, member/admin ownership rules, idempotent cancel.
- Alembic `0002_simple_planning`: `plan_entries` replaces the pre-production request/reservation tables.
- Core `/api/v1/plans` API.
- First minimal Web harness: FastAPI + Jinja2 + vendored HTMX + plain CSS at `/schedule`.
- Old request/approval/reservation product slice removed from active source/API.

## M1.1H implementation state

Branch:

`fix/m1-1h-web-hardening`

Implementation head (recorded immediately before the final M1.1H docs commit):

`21098fd8bb291893ad27443fd07d2d7b7ad0e7a2`

Accepted ADR:

`docs/adr/0001-simple-planning-model.md`

Approved hardening design:

`docs/superpowers/specs/2026-09-16-m1-1h-web-hardening-design.md`

Implementation plan:

`docs/superpowers/plans/2026-09-16-m1-1h-web-hardening.md`

Status: Tasks 1-7 are implemented, merged to `main` through PR #5 (squash commit `3e7eacc3e5850e5c10a679fbe3c15d55189788fd`) with merged-main CI green (run `35079558365`). M1.1H is NOT DEPLOYED.

## M1.1H issues (closed by the branch)

The audit items below motivated M1.1H; each is closed on `fix/m1-1h-web-hardening`:

1. `GET /api/v1/users` is still admin-only, but the member-visible Schedule requires the planning user directory for owner names/filtering.
2. A single `PlanEntry` that by itself exceeds known CPU/RAM/GPU capacity can miss an advisory warning when there are no overlapping plans.
3. Web currently interprets naive HTML `datetime-local` values as UTC instead of an explicit configured lab timezone.
4. Schedule server filtering can still render unrelated empty server groups; unknown server filters can fall back to all plans; user/owner filter is missing.
5. Web renders Cancel for every active plan and has no edit flow, despite owner/admin-only mutation semantics.
6. Local form parsing/Pydantic failures and some Core/network errors can escape as unhandled Web 500s.
7. Active API/harness documentation still has drift, including a documented server PATCH route that is not currently exposed.
8. The M1.1 cross-harness decision lacked the ADR required by repository governance; ADR 0001 now records it.

## M1.1H boundaries

M1.1H is correctness hardening only.

It does **not** add:

- production human authentication;
- header/query-string auth bypasses;
- Docker/Compose;
- Beszel;
- Runtime Collector;
- Running/Dashboard;
- deployment to the current central host or compute nodes;
- scheduler/job execution/process control.

The Web will gain a default-deny `ViewerContext` seam for correct owner/admin rendering and testing, but the real production authentication adapter remains a deployment concern for M2.

## Next gate

M1.1 and M1.1H are both merged with merged-main CI green; the previous gate list is complete.

M2 begins from the auth adapter, because both auth seams are hard default-deny and nothing is usable by a human:

1. Approve (or amend) the M2-A auth adapter design (`docs/superpowers/specs/2026-09-16-m2-auth-adapter-design.md`), then produce its implementation plan.
2. Implement the auth slice with the same task/commit/test discipline as M1.1/M1.1H.
3. Only then the deployment form (Docker/compose/`ops/`, loopback-only validation) as a separate approved slice.
4. Beszel primary monitoring + minimal read-only Runtime Collector come after; a public reverse-proxy mount is its own separately approved change.

## Important constraints

- Repository is public: never commit real private-network IPs, credentials, SSH material, tokens, usernames, private command lines, or host-specific deployment values.
- Deployment configuration must remain host-agnostic; the current deployment host is an operational choice, not a code identity.
- LabServer coordinates intent and observation; it is not a scheduler.
- Beszel will own infrastructure monitoring/history/alerts in M2; LabServer must not duplicate a telemetry platform.
- Runtime collection remains read-only.