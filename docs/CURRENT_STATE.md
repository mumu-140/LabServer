# Current State

Last updated: 2026-09-15

## Status

LabServer architecture is approved and merged to `main`. No production code has been implemented or deployed. Milestone 1 implementation planning is complete and awaiting review/execution.

## Current baseline

Architecture baseline:
- PR #1 merged to `main` as commit `9f4c983bc009fac12b7838ee6b4fd5abf4bb8b60`;
- four-harness architecture fixed (`web`, `core`, `agent`, `ops`);
- repository-wide `AGENTS.md` guardrails active;
- stable decisions recorded in `docs/PROJECT_KNOWLEDGE.md`;
- approved spec: `docs/superpowers/specs/2026-09-15-labserver-design.md`.

Current planning branch:

`plan/m1-foundation-core`

Current plan:

`docs/superpowers/plans/2026-09-15-m1-foundation-core.md`

## Milestone 1 scope

Milestone 1 implements only the central planning core:
- Python workspace and green CI baseline;
- shared contracts;
- users and logical managed-server registry;
- SQLite + Alembic migrations;
- request/reservation lifecycle;
- admin/member authorization boundary;
- advisory CPU/memory/GPU conflict engine;
- transactional/idempotent approval;
- versioned FastAPI endpoints;
- architecture-boundary tests and API documentation.

Explicitly excluded from Milestone 1:
- Lab Agent / psutil / nvitop / NVML;
- Beszel integration;
- real lab IP configuration;
- browser UI/SSE;
- reconciliation/statistics;
- production deployment.

## Next gate

Review the Milestone 1 implementation plan, then execute it task-by-task with TDD and verification after each task. Do not start Milestone 2 until Milestone 1 is merged and verified.

## Important constraints

- The GitHub repository is currently public. Never commit actual private-network IPs or operational secrets.
- V1 remains observation + planning + reconciliation + reporting. It is not a scheduler.
- Human authentication transport is not implemented in M1; protected API routes are default-deny and tests use dependency overrides.
- Managed-server data collection remains read-only and is not introduced until M2.
