# Current State

Last updated: 2026-09-15

## Status

LabServer architecture has been reviewed and approved. No production code has been implemented or deployed.

## Current branch

The approved architecture is on:

`design/initial-architecture`

and is being merged into `main` through PR #1.

## Current baseline

Completed:
- repository initialized;
- repository-wide `AGENTS.md` guardrails defined;
- four-harness architecture defined (`web`, `core`, `agent`, `ops`);
- stable project decisions recorded in `docs/PROJECT_KNOWLEDGE.md`;
- initial architecture spec added at `docs/superpowers/specs/2026-09-15-labserver-design.md`;
- architecture reviewed and approved on 2026-09-15.

Not yet implemented:
- web application;
- core API/domain model;
- Lab Agent;
- Beszel integration;
- persistence schema/migrations;
- authentication/authorization;
- deployment assets;
- tests/CI.

## Next gate

Prepare the Milestone 1 implementation plan for foundation + core planning. Implementation starts only from the reviewed plan and must preserve the approved harness boundaries.

## Active design references

- `docs/HARNESS_ARCHITECTURE.md`
- `docs/PROJECT_KNOWLEDGE.md`
- `docs/superpowers/specs/2026-09-15-labserver-design.md`

## Important constraints

- The GitHub repository is currently public. Never commit actual private-network IPs or operational secrets.
- V1 remains observation + planning + reconciliation + reporting. It is not a scheduler.
- Managed-server data collection is read-only.
