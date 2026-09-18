# Current State

Last updated: 2026-09-18

## Status

M1.1 simple planning, M1.1H web hardening, and M2-A production auth adapter are merged and verified on `main` (M1.1 commit `a2ce4a9`, M1.1H commit `3e7eacc`, M2-A commit `e8a41b5`). None is deployed.

M2-B Docker-first deployment form is implemented on branch `feat/m2-b-deployment-form` and is ready for PR review and merge. It is NOT MERGED and NOT DEPLOYED to public ingress.

## Main baseline

- M2-A was squash-merged through PR #8:
  - main commit: `e8a41b55687112b3672f48deb9887e802a602160`;
  - merged-main CI run: `35303858279` (success);
  - locked `uv sync`: success;
  - Ruff: success;
  - mypy across Core + contracts + Web: success (48 files);
  - pytest: `187 passed`;
- M1.1H was squash-merged through PR #5 (`3e7eacc3e5850e5c10a679fbe3c15d55189788fd`, merged-main CI `35079558365`);
- M1.1 was squash-merged through PR #4 (`a2ce4a924cb017c3730fa393dc9f78d6fb882407`, merged-main CI `35036877089`);
- No production public deployment has occurred.

## M2-B deployment form (branch state)

Branch: `feat/m2-b-deployment-form`

Approved design: `docs/superpowers/specs/2026-09-18-m2-b-deployment-form-design.md`  
Implementation plan: `docs/superpowers/plans/2026-09-18-m2-b-deployment-form.md`

Status: Tasks 1–6 of the implementation plan are fully implemented. NOT MERGED, NOT DEPLOYED.

### M2-B delivered

- **Packaging**: `ops/Dockerfile` multi-stage build (`python:3.13-slim` + `uv`), creating compact (128MB) image running as non-root user `labserver` (UID 1000).
- **Core Entrypoint**: `ops/entrypoint-core.sh` runs `alembic upgrade head` before launching Uvicorn, with SQLite autocommit driver isolation hardening.
- **Docker Compose**: `ops/docker-compose.yml` defines `core` and `web`, binds strictly to `127.0.0.1` (`18280` for web, `18281` for core), mounts `./data:/data`, and establishes isolated bridge network `labserver-net` with fixed subnet `10.255.30.0/24`.
- **Environment Template**: `configs/examples/.env.production.example` documents all runtime variables without secrets or deployment-specific values.
- **Web Healthcheck**: `apps/web/src/labserver_web/routes/health.py` provides `/healthz` endpoint with passing unit tests.
- **Core URL Flexibility**: `apps/web/src/labserver_web/config.py` supports both `LABSERVER_CORE_URL` and `LABSERVER_CORE_BASE_URL`.
- **Operations Tooling**:
  - `ops/bootstrap-admin.sh`: One-time admin user credential generation wrapper.
  - `ops/backup.sh`: Transactionally consistent online SQLite `.backup` to `backups/` with integrity validation.
  - `ops/restore.sh`: Validated snapshot restoration with pre-restore live database archive.
  - `ops/smoke-loopback.sh`: 8-step automated end-to-end loopback verification test.
- **Runbooks & Guides**: `docs/operations/deployment.md` and updated `docs/harnesses/ops.md`.

## Next gate

1. Open PR for M2-B to `main`.
2. Merge M2-B after final-head CI passes.
3. Update server ledger `servers/fwq10ys.md`.
4. Only then begin M2-C: Beszel primary monitoring integration.
5. Minimal read-only Runtime Collector (M2-D) follows.
6. Public reverse-proxy mount on fwq10ys Caddy is a separate approved change.

## Important constraints

- Repository is public: never commit real private-network IPs, credentials, SSH material, tokens, usernames, private command lines, or host-specific deployment values.
- Deployment configuration must remain host-agnostic; the current deployment host is an operational choice, not a code identity.
- LabServer coordinates intent and observation; it is not a scheduler.
- Beszel will own infrastructure monitoring/history/alerts in M2; LabServer must not duplicate a telemetry platform.
- Runtime collection remains read-only.
