# M2-A: Production Auth Adapter — Implementation Plan

Authoritative implementation plan for the approved design
`docs/superpowers/specs/2026-09-16-m2-auth-adapter-design.md`.

Branch: `feat/m2-a-auth-adapter`
Discipline: strict TDD, one commit per task, targeted lint/type/test after each task, full gate at the end. Deferred scope must be listed in `docs/CURRENT_STATE.md` at delivery (delivery-discipline rule in `docs/PROJECT_KNOWLEDGE.md`).

Standing rules that apply unchanged:

- Production auth is default-deny; no `X-User`, query admin, hardcoded admin, dev bypass, anonymous admin.
- Routes stay thin; web stays HTTP/contracts-only; `0001`/`0002` migrations untouched.
- Version pins: do not modernize dependencies; the only new runtime dependency is `argon2-cffi` (pinned at implementation time via normal `uv lock/sync`).
- Public repo: no credentials, secrets, or real hostnames/IPs; test data only.

## Task 1 — Auth contracts

`packages/contracts/src/labserver_contracts/auth.py`:

- `LoginRequest(username: TrimmedText, password: str)` (write model).
- `SessionRead(user_id: UUID, role: UserRole)` (read model) — the payload of `POST /auth/login` and `GET /auth/me`.
- `UserPasswordSet(password: str)` in `users.py` — admin password rotation body.

Failing tests first: contract validation (blank username rejected, password min length, read model round-trip). Commit: `feat: add auth contracts`.

## Task 2 — Persistence: migration `0003_auth`

- `UserModel` gains nullable `password_hash` (nullable column; users without credentials cannot log in).
- New `AuthSessionModel` (`auth_sessions`): `token_hash: str` primary key (SHA-256 hex of the raw token), `user_id` FK → `users.id`, `created_at`, `expires_at` (UTC).
- New `0003_auth.py` migration adding the column and the table; `0001`/`0002` untouched.
- `AuthSessionRepository`: `add`, `get(token_hash)`, `delete(token_hash)`, `delete_expired(now)`.

Failing tests first: fresh DB → head; `0002` DB → `0003` head; column existence/nullability; FK enforcement; session add/get/delete; expired pruning. Commit: `feat: persist auth credentials and sessions`.

## Task 3 — Password hashing port

`services/core/src/labserver_core/application/passwords.py`:

- `PasswordHasher` protocol (`hash(raw) -> str`, `verify(raw, encoded) -> bool`).
- `Argon2PasswordHasher` backed by `argon2-cffi` (`PasswordHasher` from argon2). No hand-rolled hashing.

Add `argon2-cffi` to core dependencies with a pinned version via `uv lock`; no other lockfile churn. Failing tests first: hash/verify round-trip; wrong password fails; hash is salted (two hashes of the same raw differ). Commit: `feat: add argon2 password hashing`.

## Task 4 — Auth application service

`services/core/src/labserver_core/application/auth_service.py`:

- `AuthService(auth_sessions, users, hasher, clock, settings)` with:
  - `login(username, password) -> SessionContext` — uniform failure (`UnknownCredentials`) for unknown user, disabled user, and wrong password; stores raw token only transiently, persists SHA-256 hash with `expires_at = now + TTL`.
  - `resolve(token) -> CurrentActor` — hash lookup, expiry check, `require_active_actor` re-check against the stored user (disabled/role-changed users fail immediately).
  - `logout(token)` — idempotent delete.
  - `has_enabled_admin()` and `set_password(actor, user_id, raw)` — admin-only; hashes via the port, never persists raw.
- Session TTL from `Settings.session_ttl_hours` (env `LABSERVER_SESSION_TTL_HOURS`, default `168`); `Settings` gains the field.

Failing tests first: login ok; unknown user ≡ wrong password ≡ disabled user (identical error); expired session rejected; logout invalidates; disabled mid-session fails; admin gate on `set_password`; TTL honored. Fake hasher + fake clock in tests. Commit: `feat: add auth application service`.

## Task 5 — Core HTTP API

- `routes/auth.py`: `POST /api/v1/auth/login` (sets `labserver_session` cookie: `HttpOnly`, `SameSite=Lax`, `Path=/`, `Secure` from `Settings.cookie_secure`, env `LABSERVER_COOKIE_SECURE`, default `false`), `POST /api/v1/auth/logout` (204, clears cookie), `GET /api/v1/auth/me`.
- `get_current_actor` becomes the real adapter: cookie → `AuthService.resolve` → `CurrentActor`; missing/invalid/expired → 401 with the stable error envelope.
- `routes/users.py` gains `POST /api/v1/users/{user_id}/password` (admin-only, `require_admin`).
- Cookie domain stays unset (`None`) per design D3.

Failing tests first: 401 without cookie; login/me/logout happy path; 401 wrong password indistinguishable from unknown user; disabled user 401; admin-only password route (401/403); envelope conformance for 401/403/404/422. Commit: `feat: expose auth API`.

## Task 6 — Admin bootstrap CLI

`services/core/src/labserver_core/bootstrap_admin.py`, runnable as `python -m labserver_core.bootstrap_admin <username>`:

- Refuses (exit 1, clear message) when any enabled admin already exists.
- On success: creates the admin user if absent (or upgrades an existing user to admin only if explicitly passed `--promote`), generates a random password (`secrets`), prints it exactly once to stdout, stores only the hash.

Failing tests first: refuses on existing enabled admin; succeeds on empty DB; output contains the password once and DB stores no plaintext. Commit: `feat: add admin bootstrap CLI`.

## Task 7 — Web login surface

- `POST /login` (form) → Core `POST /auth/login` → forward Core's `Set-Cookie` to the browser unchanged (Web stores no identity state); render login errors from the normalized error path (no 500).
- `GET /login` renders the form even while anonymous (the only anonymous-allowed page).
- `POST /logout` → Core `POST /auth/logout` → clear cookie → redirect to `/login`.
- `get_current_viewer` becomes: read cookie → Core `GET /auth/me` → `ViewerContext(user_id, role)`; any failure → 401. Shape unchanged; owner/admin controls keep working.
- Minimal plain-CSS login template consistent with the existing harness.

Failing tests first: login page renders anonymously; failed login shows a normalized error; successful login round-trip sets the cookie; viewer resolves through Core; logout clears; unauthenticated `/schedule` still 401; Core unavailable normalized; no new Web-side persistence; AST boundary guard still passes. Commit: `feat: add web login surface`.

## Task 8 — Docs and state

- API docs: document the three auth endpoints and the password-rotation endpoint.
- `docs/CURRENT_STATE.md`: M2-A implemented on the branch, PR under review, NOT MERGED, NOT DEPLOYED; deferred items listed explicitly (none expected; any deviation recorded here).
- Runbook note (docs only): bootstrap CLI usage and the `Secure`-cookie production requirement.

Commit: `docs: finalize M2-A auth adapter`.

## Final gate (before PR)

```bash
uv sync --all-packages --dev --locked
uv run ruff check .
uv run mypy services/core/src packages/contracts/src apps/web/src
uv run pytest -q
```

Plus: fresh DB → head and `0002` → `0003` migration; `/healthz` smoke; auth API smoke (bootstrap CLI → login → me → logout) on loopback with `NO_PROXY=127.0.0.1,localhost`; `/login` Web smoke; architecture/terminology/secret scans.

Then push the branch and open the PR. Do not describe M2-A as merged or deployed until main contains it and merged-main CI is green.
