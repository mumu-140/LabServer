# Ops Harness Guide

Scope: `ops/`, deployment templates under `configs/examples/`, and operational runbooks under `docs/operations/`.

## Owns

- Service/process definitions.
- Safe environment/configuration templates.
- Reverse proxy/TLS configuration where used.
- Health checks.
- Backup/restore.
- Upgrade and rollback procedures.
- Deployment topology documentation.

## Must not own

- Domain/business logic.
- UI behavior.
- Agent collection logic.
- Production secrets inside repository files.

## Active Assets (M2-B)

- `ops/Dockerfile`: Multi-stage, non-root (UID 1000) packaging using `python:3.13-slim` and locked `uv` workspace dependencies.
- `ops/entrypoint-core.sh`: Runs Alembic migrations (`alembic upgrade head`) before starting Core FastAPI service.
- `ops/docker-compose.yml`: Production composition defining `core` and `web`, fixed `10.255.30.0/24` subnet, `./data` volume, and `127.0.0.1` loopback bindings.
- `configs/examples/.env.production.example`: Safe environment template with variable descriptions.
- `ops/bootstrap-admin.sh`: Wrapper for one-time admin user creation.
- `ops/backup.sh` & `ops/restore.sh`: Safe, transactionally consistent online SQLite backup and restore utilities.
- `ops/smoke-loopback.sh`: Comprehensive end-to-end loopback verification against `127.0.0.1:18280`.
- `docs/operations/deployment.md`: Production deployment, bootstrap, backup/restore, and upgrade runbook.

## Configuration rules

- Real server IPs, tokens, passwords, SSH material, and deployment-specific usernames stay outside Git.
- Checked-in configuration uses obvious placeholders such as `<private-ip>`.
- Prefer logical keys (`fwq10`) in application configuration and map them to endpoints at runtime.
- Every required environment variable must be documented in a safe example file.
- Fail startup on missing required secrets/configuration rather than silently using insecure defaults.

## Operational invariants

- One managed host being down must not prevent central LabServer from starting.
- Agent/network requests have explicit connect/read timeouts.
- Services have health endpoints/checks that do not depend on all managed hosts being online.
- SQLite database and required persistent data have a documented backup and restore path before production use.
- Upgrade instructions include rollback steps.
- Development defaults must never target real lab servers.

## Deployment preference

Keep V1 topology small: central LabServer service + SQLite + optional Beszel Hub, with one lightweight read-only Lab Agent per managed host. Avoid introducing orchestration infrastructure unless measured operational needs justify it.

## Verification before deployment

- configuration contains no placeholder accidentally left unresolved;
- no secret appears in logs or generated manifests;
- database backup exists and restore was smoke-tested;
- agents are read-only and run with the minimum practical privileges;
- health/freshness behavior has been tested with at least one unreachable host;
- private-network access rules match the documented topology.
