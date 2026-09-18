# Current State

Last updated: 2026-09-18

## Status

M1.1 simple planning and M1.1H web hardening are merged and verified on `main` (PR #5 commit `3e7eacc`, PR #7 commit `752061f`). Neither is deployed.

M2-A production auth adapter is implemented on branch `feat/m2-a-auth-adapter` and is ready for PR review and merge (PR #8). It is NOT MERGED and NOT DEPLOYED.

## Main baseline

M1.1H was squash-merged through PR #5:

- main commit: `3e7eacc3e5850e5c10a679fbe3c15d55189788fd`;
- merged-main CI run: `35079558365` (success);
- locked `uv sync`: success;
- Ruff: success;
- mypy across Core + contracts + Web: success (42 files);
- pytest: `141 passed`;
- PR #7 (`752061fca1006a542bdd9b1ba6ae59d6e2df9f86`) recorded M1.1H merged state;
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

## M1.1H hardening delivered

- Accepted ADR: `docs/adr/0001-simple-planning-model.md`
- Approved hardening design: `docs/superpowers/specs/2026-09-16-m1-1h-web-hardening-design.md`
- Implementation plan: `docs/superpowers/plans/2026-09-16-m1-1h-web-hardening.md`
- All 7 hardening tasks implemented and merged to `main` via PR #5 (`3e7eacc`).

## M2-A auth adapter (branch state)

Branch: `feat/m2-a-auth-adapter`

Approved design: `docs/superpowers/specs/2026-09-16-m2-auth-adapter-design.md`
Implementation plan: `docs/superpowers/plans/2026-09-17-m2-a-auth-adapter.md`

Status: Tasks 1–8 of the implementation plan are fully implemented. Ready for merge. NOT MERGED, NOT DEPLOYED.

### M2-A delivered

- **Auth contracts**: `LoginRequest`, `SessionRead`, `UserPasswordSet` in `labserver_contracts`.
- **Persistence**: migration `0003_auth` adding nullable `password_hash` to `users` and `auth_sessions` table (token stored as SHA-256 hash). `0001`/`0002` untouched.
- **Password hashing port**: `Argon2PasswordHasher` via `argon2-cffi`.
- **Auth application service**: `AuthService` handling login (uniform 401), session resolution, logout, enabled admin check, and password rotation.
- **Core HTTP API**: `/api/v1/auth/login`, `/api/v1/auth/logout`, `/api/v1/auth/me`, `/api/v1/users/{user_id}/password`. Real `get_current_actor` adapter reading session cookie.
- **Admin bootstrap CLI**: `python -m labserver_core.bootstrap_admin <username> [--promote]`. Refuses if enabled admin exists. Generates random password, prints once, stores only hash.
- **Web UI login surface**: `/login` (GET/POST), `/logout` (POST), `get_current_viewer` resolving cookie through Core `/me`.
- **Deferred items**: None. All tasks from the plan delivered.

### Runbook note (operations)

- **Admin Bootstrap**: On an initial deployment or empty database, run `python -m labserver_core.bootstrap_admin <username>` to generate the initial admin credentials. The printed password is never stored in plaintext.
- **Cookie Security**: Set `LABSERVER_COOKIE_SECURE=true` in production behind TLS/HTTPS reverse proxies.

## Next gate

1. Verify complete test suite, lint, mypy, migration smoke, loopback smoke, architecture/terminology scans.
2. Merge PR #8 for M2-A to `main` once CI passes.
3. Only then begin M2-B: deployment form (Docker/Compose/`ops/`, loopback-only validation).
4. Beszel primary monitoring + minimal read-only Runtime Collector come after.
5. Public reverse-proxy mount on fwq10ys Caddy is a separate approved change.

## Important constraints

- Repository is public: never commit real private-network IPs, credentials, SSH material, tokens, usernames, private command lines, or host-specific deployment values.
- Deployment configuration must remain host-agnostic; the current deployment host is an operational choice, not a code identity.
- LabServer coordinates intent and observation; it is not a scheduler.
- Beszel will own infrastructure monitoring/history/alerts in M2; LabServer must not duplicate a telemetry platform.
- Runtime collection remains read-only.
