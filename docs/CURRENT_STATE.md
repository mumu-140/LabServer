# Current State

Last updated: 2026-09-15

## Status

LabServer is in the architecture/design phase. No production code has been implemented or deployed.

## Current branch

Design work is being prepared on:

`design/initial-architecture`

## Current baseline

Completed:
- repository initialized;
- repository-wide `AGENTS.md` guardrails defined;
- four-harness architecture defined (`web`, `core`, `agent`, `ops`);
- stable project decisions recorded in `docs/PROJECT_KNOWLEDGE.md`;
- initial architecture spec is being added under `docs/superpowers/specs/`.

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

The next step is human review of the initial design spec. Implementation planning must not begin until the architecture/spec is approved.

## Active design references

- `docs/HARNESS_ARCHITECTURE.md`
- `docs/PROJECT_KNOWLEDGE.md`
- `docs/superpowers/specs/2026-09-15-labserver-design.md`

## Important constraints

- The GitHub repository is currently public. Never commit actual private-network IPs or operational secrets.
- V1 remains observation + planning + reconciliation + reporting. It is not a scheduler.
- Managed-server data collection is read-only.
