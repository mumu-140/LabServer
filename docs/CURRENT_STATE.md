# Current State

Last updated: 2026-09-15

## Status

Milestone 1 central planning core is merged and verified on `main`. It has not been deployed to lab servers.

The product requirement has since been clarified: planning/scheduling is only a lightweight shared declaration of intended use, not an approval, reservation-lock, queue, or scheduler workflow. M1.1 is therefore a pre-deployment simplification milestone.

## Main baseline

Merged baseline:
- PR #1 architecture baseline: `9f4c983bc009fac12b7838ee6b4fd5abf4bb8b60`;
- PR #2 M1 implementation plan: `f3180f992205375f19f9eacace049890a6047e78`;
- PR #3 M1 implementation squash-merged as `faa19b09c4d5ad9ca34edd55527bef401fdcaf4a`;
- merged-main CI run `34942758598`: completed / success;
- locked sync, Ruff, mypy, and pytest all passed on merged `main`.

No production deployment has occurred.

## Current design work

Branch:

`docs/m1-1-simple-planning-design`

Approved design:

`docs/superpowers/specs/2026-09-15-m1-1-simple-planning-design.md`

Implementation plan:

`docs/superpowers/plans/2026-09-15-m1-1-simple-planning.md`

Status: design approved by the user; implementation plan written and ready for review/execution. No M1.1 implementation code has been written on this branch.

## M1.1 purpose

Simplify the planning model before deployment:
- replace the public `TaskRequest -> approval -> Reservation` workflow with one `PlanEntry` concept;
- publishing a plan means only "I intend to use these resources during this time window";
- members can create/edit/cancel their own plans;
- admins can correct any plan;
- conflicts remain advisory and never lock or dispatch resources;
- add a simple shared Schedule web surface;
- remove approval/rejection language and scheduler semantics.

The current M1 request/reservation implementation remains on `main` until M1.1 is implemented, tested, reviewed, and merged.

## M1.1 implementation sequence

The approved plan uses eight gated tasks:
1. plan contracts;
2. `PlanEntry` domain + advisory conflict engine;
3. `plan_entries` migration/repository/UoW;
4. plan application service + ownership authorization;
5. `/api/v1/plans` HTTP surface;
6. minimal FastAPI/Jinja2/HTMX `/schedule` web harness;
7. removal of obsolete request/approval/reservation product code;
8. documentation + migration + full CI merge gate.

The old slice is removed only after the replacement path is green.

## M2 direction after M1.1

M2 will add observability/deployment while preserving the lightweight coordination model:
- Docker-first deployment;
- Beszel as the primary infrastructure-monitoring source of truth;
- a minimal read-only Runtime Collector only for user/PID/GPU-process attribution not provided by Beszel;
- Running view combining monitoring state with runtime ownership;
- host-specific deployment values remain outside Git and compose/templates stay host-agnostic.

The current central deployment machine is an operational choice and must not be hard-coded into repository scripts or compose files.

## Important constraints

- The GitHub repository is public. Never commit real private-network IPs, credentials, SSH material, tokens, usernames, or private command lines.
- Deployment configuration must remain host-agnostic.
- LabServer is not a scheduler. It coordinates intent, observes current use, reconciles where useful, and reports.
- Beszel owns infrastructure monitoring/history/alerts; LabServer must not duplicate a telemetry platform.
- Runtime collection is read-only. No remote shell, process kill, renice, package installation, or job submission.
- Human authentication transport is not yet implemented; protected routes remain default-deny until an explicit trusted adapter is selected.

## Next gate

1. Review/execute the approved M1.1 implementation plan.
2. Verify migrations, Ruff, mypy, pytest, architecture/terminology guards, and final PR CI.
3. Merge M1.1 only after the exact final head is green.
4. Then finalize the M2 Docker + Beszel + Runtime Collector design and implementation plan.
