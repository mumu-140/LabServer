# Current State

Last updated: 2026-09-18

## Status

M1.1 simple planning, M1.1H web hardening, M2-A production auth adapter, and M2-B Docker-first deployment form are merged and verified on `main` (M1.1 commit `a2ce4a9`, M1.1H commit `3e7eacc`, M2-A commit `e8a41b5`, M2-B PR #9). None is exposed to public ingress.

M2-C Beszel monitoring integration & Web host dashboard is fully implemented on branch `feat/m2-c-beszel-adapter`, verified via complete test suite (208 tests passing, strict typing, zero lint warnings) and live 11-step loopback smoke testing with Docker Compose on `fwq10ys`. Ready for PR review and merge.

## Main baseline

- M2-B was squash-merged through PR #9:
  - Packaging: Multi-stage `ops/Dockerfile` with `uv` (`python:3.13-slim`), unprivileged user `labserver` (UID 1000).
  - Compose stack: `core` + `web` bound strictly to loopback `127.0.0.1` (`18281`, `18280`) on isolated `labserver-net` (`10.255.30.0/24`).
  - Ops tooling: `bootstrap-admin.sh`, `backup.sh`, `restore.sh`, `smoke-loopback.sh`.
- M2-A was squash-merged through PR #8 (`e8a41b55687112b3672f48deb9887e802a602160`, merged-main CI green);
- M1.1H was squash-merged through PR #5 (`3e7eacc3e5850e5c10a679fbe3c15d55189788fd`);
- M1.1 was squash-merged through PR #4 (`a2ce4a924cb017c3730fa393dc9f78d6fb882407`);
- No production public deployment has occurred.

## M2-C Beszel monitoring integration (branch state)

Branch: `feat/m2-c-beszel-adapter`

Approved design: `docs/superpowers/specs/2026-09-18-m2-c-beszel-adapter-design.md`  
Implementation plan: `docs/superpowers/plans/2026-09-18-m2-c-beszel-adapter.md`

Status: Tasks 1–7 implemented, tested, and container-verified.

### M2-C delivered

- **Contracts**: `packages/contracts/src/labserver_contracts/monitoring.py` defining `HostStatus` (`UP`, `DOWN`, `UNREACHABLE`, `UNKNOWN`), `FreshnessStatus` (`FRESH`, `STALE`, `UNKNOWN`), `GpuMetricsRead`, `HostMetricsRead`, `ServerDashboardCard`, and `DashboardRead`.
- **Core Monitoring Adapter**: `services/core/src/labserver_core/adapters/monitoring.py` with `HostMetricsProvider` protocol, `FakeHostMetricsProvider`, and production-grade `BeszelAdapter` (PocketBase REST API, automatic auth token acquisition and caching, 15s in-memory cache TTL, 5s timeout, per-system record parsing, status and freshness derivation, graceful fallback).
- **Core API & Service**: `services/core/src/labserver_core/application/monitoring_service.py` assembling multi-server dashboard with near-term scheduled plan coordination. Exposed at `GET /api/v1/monitoring/dashboard` and `GET /api/v1/monitoring/servers/{server_key}` with session authentication.
- **Web Client & Routes**: `apps/web/src/labserver_web/routes/dashboard.py` providing `GET /` and `GET /dashboard` routes with unauthenticated default-deny and graceful error presentation.
- **Web UI & Navigation**: Enhanced navigation bar (`Dashboard` / `Schedule` tabs with active indicator, username, logout) and responsive server card dashboard rendering CPU, Memory, Disk gauges, GPU tags, system load/uptime, active plan indicators, and direct Beszel deep-links.
- **Fleet Server Seeding & Ops**: `services/core/src/labserver_core/seed_servers.py` and `ops/seed-servers.sh` idempotently initializing default fleet servers (`fwq10`, `fwq51`, `fwq56`, `fwq57`) with actual hardware capacities.
- **Compose & Smoke Verification**: `ops/docker-compose.yml` updated with `host.docker.internal:host-gateway` and Beszel environment options. `ops/smoke-loopback.sh` updated to 11 automated checks, verified end-to-end against live container stack on `fwq10ys`.

## Next gate

1. Open PR for M2-C to `main`.
2. Merge M2-C after CI passes.
3. Update server ledger `servers/fwq10ys.md`.
4. Proceed to M2-D: Minimal read-only Runtime Collector (local GPU/process inspection).
5. Public reverse-proxy mount on fwq10ys Caddy is a separate approved change.

## Important constraints

- Repository is public: never commit real private-network IPs, credentials, SSH material, tokens, usernames, private command lines, or host-specific deployment values.
- Deployment configuration must remain host-agnostic; the current deployment host is an operational choice, not a code identity.
- LabServer coordinates intent and observation; it is not a scheduler.
- Beszel owns infrastructure monitoring/history/alerts in M2; LabServer must not duplicate a telemetry platform.
- Runtime collection remains read-only.
