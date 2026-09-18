# Current State

Last updated: 2026-09-18

## Status

M1.1 simple planning, M1.1H web hardening, M2-A production auth adapter, M2-B Docker-first deployment form, and M2-C Beszel monitoring integration are merged and verified on `main` (M1.1 commit `a2ce4a9`, M1.1H commit `3e7eacc`, M2-A commit `e8a41b5`, M2-B PR #9, M2-C PR #10 `43490c4`). None is exposed to public ingress.

M2-D Minimal read-only Runtime Collector & "Running" Web view is fully implemented on branch `feat/m2-d-runtime-collector`, verified via complete test suite (229 tests passing, strict typing, zero lint warnings) and live 14-step loopback smoke testing with Docker Compose on `fwq10ys`, along with hardware verification across live GPU hosts (`fwq57`, `fwq51`). Ready for PR review and merge.

## Main baseline

- M2-C was squash-merged through PR #10 (`43490c4`):
  - Beszel primary monitoring integration & Web host dashboard.
  - Fleet server seeding (`ops/seed-servers.sh`).
- M2-B was squash-merged through PR #9:
  - Packaging: Multi-stage `ops/Dockerfile` with `uv` (`python:3.13-slim`), unprivileged user `labserver` (UID 1000).
  - Compose stack: `core` + `web` bound strictly to loopback `127.0.0.1` (`18281`, `18280`) on isolated `labserver-net` (`10.255.30.0/24`).
  - Ops tooling: `bootstrap-admin.sh`, `backup.sh`, `restore.sh`, `smoke-loopback.sh`.
- M2-A was squash-merged through PR #8 (`e8a41b55687112b3672f48deb9887e802a602160`);
- M1.1H was squash-merged through PR #5 (`3e7eacc3e5850e5c10a679fbe3c15d55189788fd`);
- M1.1 was squash-merged through PR #4 (`a2ce4a924cb017c3730fa393dc9f78d6fb882407`);
- No production public deployment has occurred.

## M2-D Minimal read-only Runtime Collector (branch state)

Branch: `feat/m2-d-runtime-collector`

Approved design: `docs/superpowers/specs/2026-09-18-m2-d-runtime-collector-design.md`  
Implementation plan: `docs/superpowers/plans/2026-09-18-m2-d-runtime-collector.md`

Status: Tasks 1–7 implemented, tested, and container-verified.

### M2-D delivered

- **Contracts**: `packages/contracts/src/labserver_contracts/runtime.py` defining `RuntimeStatus` (`active`, `idle`, `unavailable`), `RuntimePlanCorrelation` (`matched`, `unplanned`, `idle_reservation`), `GpuProcessInfo`, `GpuDeviceRuntime`, `HostRuntimeReport`, `HostRuntimeRead`, and `RuntimeOverviewRead`.
- **Core In-Memory Store & Service**: `services/core/src/labserver_core/application/runtime_store.py` providing thread-safe report cache with TTL freshness calculation; `services/core/src/labserver_core/application/runtime_service.py` correlating active ONGOING plans (`server_id`, `gpu_ids`, `plan.owner_id == proc.username`) against reported compute processes and tracking active reservations on idle GPUs.
- **Core Runtime API**: `services/core/src/labserver_core/api/routes/runtime.py` implementing `POST /api/v1/runtime/report` (authenticated by shared collector token), `GET /api/v1/runtime/overview`, and `GET /api/v1/runtime/servers/{server_key}` (authenticated by session).
- **Standalone Host Collector Script**: `ops/labserver-collector.py` - lightweight, zero-dependency Python 3.8+ script querying `nvidia-smi` devices and compute processes with instant OS username resolution (`pwd.getpwuid(os.stat("/proc/{pid}").st_uid).pw_name`), graceful fallback on non-GPU hosts, and verified live on multi-GPU production nodes (`fwq57`, `fwq51`).
- **Web Client & "Running" UI**: `apps/web/src/labserver_web/routes/running.py` providing `GET /running` with unauthenticated default-deny; `apps/web/src/labserver_web/templates/running/index.html` rendering live server status badges, GPU utilization and temperature cards, compute process tables with color-coded plan correlation (`● Matched`, `▲ Unplanned`), and active scheduled intent.
- **Ops & Smoke Verification**: `configs/examples/.env.production.example` and `ops/docker-compose.yml` updated with collector configuration. `ops/smoke-loopback.sh` expanded to 14 automated loopback tests covering unauthenticated deny, runtime report ingestion, live Web rendering, and session invalidation.

## Next gate

1. Open PR for M2-D to `main`.
2. Merge M2-D after GitHub Actions CI passes.
3. Update server ledger `servers/fwq10ys.md`.
4. Review M2 milestone completion and next steps.

## Important constraints

- Repository is public: never commit real private-network IPs, credentials, SSH material, tokens, usernames, private command lines, or host-specific deployment values.
- Deployment configuration must remain host-agnostic; the current deployment host is an operational choice, not a code identity.
- LabServer coordinates intent and observation; it is not a scheduler.
- Beszel owns infrastructure monitoring/history/alerts in M2; LabServer must not duplicate a telemetry platform.
- Runtime collection remains read-only.
