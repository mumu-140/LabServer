# Current State

Last updated: 2026-09-15

## Status

Milestone 1 central planning core has been implemented on `feat/m1-foundation-core` and is under final review in PR #3. It is not yet merged to `main` and nothing has been deployed to lab servers.

## Main baseline

Merged architecture/planning baseline:
- PR #1 merged as `9f4c983bc009fac12b7838ee6b4fd5abf4bb8b60`;
- PR #2 merged as `f3180f992205375f19f9eacace049890a6047e78`;
- four-harness architecture fixed (`web`, `core`, `agent`, `ops`);
- repository-wide `AGENTS.md` guardrails active;
- approved spec: `docs/superpowers/specs/2026-09-15-labserver-design.md`;
- M1 plan: `docs/superpowers/plans/2026-09-15-m1-foundation-core.md`.

## Active implementation

Branch:

`feat/m1-foundation-core`

Pull request:

`#3 feat: implement milestone 1 foundation and core`

## Milestone 1 implemented scope

M1 contains only the central planning core:
- Python 3.13 + uv workspace and locked dependency graph;
- GitHub Actions CI with locked sync, Ruff, mypy, and pytest;
- shared Pydantic contracts and canonical enums;
- pure request lifecycle/domain rules;
- logical managed-server registry using stable keys rather than IP identity;
- SQLite persistence with Alembic migration from the first schema;
- SQLite foreign-key enforcement and repository/unit-of-work boundaries;
- default-deny human authorization dependency with `admin` / `member` application rules;
- advisory CPU, memory, aggregate GPU, and explicit GPU-device conflict evaluation;
- transactional and idempotent request approval into reservations;
- versioned FastAPI routes under `/api/v1` plus `/healthz`;
- stable machine-readable API error envelope;
- architecture-boundary tests preventing routes from importing persistence/SQLAlchemy and contracts from depending on core;
- Core v1 API documentation at `docs/api/core-v1.md`.

## Verification evidence

Fresh local verification of the M1 tree:
- fresh empty SQLite database upgraded successfully to Alembic head;
- expected tables present: `alembic_version`, `audit_events`, `managed_servers`, `reservations`, `task_requests`, `users`;
- API smoke suite: 5 passed;
- full suite: 82 passed;
- Ruff: all checks passed;
- mypy: success across 36 source files.

Remote verification before this status-only update:
- GitHub Actions run `34935656728`: completed / success;
- locked `uv sync`, Ruff, mypy, and pytest all succeeded.

The final PR head must be re-verified by CI after this documentation update before merge.

## Explicitly not implemented in Milestone 1

- Lab Agent / `psutil` / `nvitop` / NVML;
- Beszel integration;
- real lab IP configuration;
- browser UI or SSE;
- live process/user observation;
- plan-vs-actual reconciliation;
- usage/statistics aggregation;
- production deployment;
- remote shell, process control, job submission, or scheduler behavior.

## Next gate

1. Complete final PR #3 review and verify its latest head.
2. Squash-merge M1 only after review approval.
3. Verify CI on merged `main`.
4. Only then begin Milestone 2: read-only Lab Agent + Running view, preserving the approved agent/core/web boundaries.

## Important constraints

- The GitHub repository is currently public. Never commit actual private-network IPs or operational secrets.
- V1 remains observation + planning + reconciliation + reporting. It is not a scheduler.
- Human authentication transport is not implemented in M1; protected API routes are default-deny and tests use dependency overrides.
- Managed-server data collection remains read-only and is not introduced until M2.
