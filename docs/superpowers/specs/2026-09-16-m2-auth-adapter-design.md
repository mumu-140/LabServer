# M2-A: Production Auth Adapter — Design

Status: PROPOSED (awaiting approval)
Date: 2026-09-16
Depends on: M1.1H (`fix/m1-1h-web-hardening`) — uses the `ViewerContext` seam and owner/admin rendering it introduced.

## Problem

Both authentication seams are hard default-deny:

- Core `get_current_actor()` (`services/core/src/labserver_core/api/dependencies.py`) raises 401 unconditionally.
- Web `get_current_viewer()` (`apps/web/src/labserver_web/auth.py`) raises 401 unconditionally.

Every real request therefore gets 401. The `User` entity has no credential field; users exist only as metadata. Until a production human authentication transport exists, nothing can be used.

## Goals

1. A human can log in with a username and password and use the Web schedule page.
2. Core remains the single authority for identity and authorization; Web never decides authorization itself.
3. Default-deny stays the default: without a valid session every request is 401.
4. Disabled users lose access immediately (no lingering sessions).

## Non-goals (this slice)

- API tokens / machine-to-machine auth (later slice if needed).
- Password self-service reset, email flows, MFA.
- SSO / OIDC / Cloudflare Access integration.
- Rate limiting beyond the reverse proxy's capability (deployment slice concern).
- Anything about Docker, Caddy, or the deployment host (separate M2 slices).

## Red lines (unchanged)

- No `X-User` or any unauthenticated identity header.
- No query-parameter admin, hardcoded admin, dev bypass, or anonymous admin.
- Credentials and session secrets never enter the repository; only position pointers in docs.
- Web consumes Core only over HTTP; Web has no database access.

## Key decisions

### D1 — Credential type: username + password (argon2id)

Options considered:

- **(a) Password per user** — matches the lab reality: a handful of trusted members, admin already creates users via `POST /api/v1/users`.
- (b) Per-user API tokens — good for scripts, poor for humans on a web page.
- (c) Proxy-issued identity (forward auth) — couples identity to a specific infrastructure the repository must stay agnostic about.

Recommendation: **(a)**. Hashing via `argon2-cffi` (pinned version at implementation time); no hand-rolled hashing. This is the only new runtime dependency this slice adds.

### D2 — Session mechanism: server-side sessions in SQLite

Options considered:

- **(a) Server-side session table** — a token maps to a session row; every request validates the session and re-checks `user.enabled`/`role`. Revocation on disable/delete is immediate and unconditional.
- (b) Signed cookie (itsdangerous) — fewer moving parts, but needs a managed secret and cannot reliably revoke access for a disabled user without key rotation.

Recommendation: **(a)**. It composes directly with the existing `require_active_actor` rule (role/enabled re-checked against the stored user on every request) and needs no secret key management. Expiry: fixed sliding TTL (default 7 days, configurable via Core config); expired rows pruned opportunistically.

### D3 — Where login lives: Core owns auth endpoints; Web proxies the experience

Core (authoritative):

```text
POST /api/v1/auth/login      { username, password }  -> 200 { user_id, role } + Set-Cookie (session token, HttpOnly, SameSite=Lax, Secure in production)
POST /api/v1/auth/logout                             -> 204 (requires valid session)
GET  /api/v1/auth/me                                 -> 200 { user_id, role } (requires valid session)
```

- Sessions are validated server-side; login rate limiting is deferred to the deployment slice, but failed logins must not leak whether the username exists (uniform 401).
- `get_current_actor()` is replaced by a real adapter: session cookie → session row → `require_active_actor` → `CurrentActor`. The 401 default remains for missing/invalid/expired sessions.

Web (presentation only):

- `/login` page (form posts username/password to Web, Web calls Core `POST /auth/login`, Web stores nothing — the Core `Set-Cookie` is forwarded; cookie path must cover both Web and Core routes behind the future single reverse proxy).
- `get_current_viewer()` becomes: read cookie → Core `GET /auth/me` → `ViewerContext(user_id, role)`; any failure → 401.
- Logout link → Core `POST /auth/logout` → clear cookie.
- No new Web-side identity state; `ViewerContext` shape is unchanged.

Cookie hosting note: today Core and Web run as separate processes; the cookie is issued by Core and presented by both services. This only works cleanly once both share one public origin (the M2 deployment slice's single reverse proxy). For loopback testing, Web and Core are reached on `127.0.0.1` at different ports — the design requires an explicit `cookie domain=None, path=/` cookie set by Core and accepted on both loopback ports during development; production mounting is the deployment slice's responsibility and must present one origin.

### D4 — Admin bootstrap: one-time CLI, not in HTTP

`python -m labserver_core bootstrap-admin <username>`:

- Refuses to run if any enabled admin already exists (bootstrap is a wedge, not a backdoor).
- Generates a random password, prints it exactly once to stdout, stores only the argon2 hash.
- Documented in the deployment slice's ops runbook; the printed password never enters any file.

### D5 — Persistence: migration `0003_auth`

- `users` gains `password_hash: str | null` (nullable: users without credentials simply cannot log in; admin can set/reset a password).
- New table `auth_sessions`: `token_hash` (primary key, SHA-256 of the raw token), `user_id` (FK), `created_at`, `expires_at`. Raw tokens are never stored.
- `0001`/`0002` migrations remain untouched, per standing rule.
- New admin operations: `POST /api/v1/users/{id}/password` (admin sets/rotates a user's password; user password self-change is a later nicety).

## Test topics (implementation plan will expand)

- Contract: login request/response, `me`, logout.
- API: 401 without session; 401 wrong password (indistinguishable from unknown user); disabled user denied at login and mid-session; admin-only password rotation; 403/401/404/422 envelope conformance.
- Session: expiry pruning; logout invalidates; token stored hashed.
- Bootstrap CLI: refuses when an enabled admin exists; succeeds on empty DB; password printed once and never persisted in plaintext.
- Web: login page renders; unauthenticated `/schedule` still 401; after login the viewer identity drives owner/admin controls; Core unavailable → normalized error (no 500 leak).
- Boundary: Web still imports no Core/SQLAlchemy; routes stay thin; terminology guard unchanged.

## Open questions for approval

1. Confirm D1 (password) and D2 (server-side sessions) as recommended.
2. Confirm the session TTL default (proposed 7 days, sliding).
3. Confirm admin password rotation endpoint is admin-only in this slice (no self-service).
4. Confirm this slice ships only auth — deployment form (Docker/compose/ops) and reverse-proxy mount remain separate, separately approved slices.
