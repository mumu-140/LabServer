# Web Harness Guide

Scope: `apps/web/`

## Owns

- Dashboard, Servers, Schedule, Statistics UI.
- The shared `/schedule` page: presentation only, rendered from the Core API contracts.
- Form handling and presentation validation.
- Rendering current-state updates from core APIs/SSE.
- Accessibility and responsive layout.

## Must not own

- Planning semantics: publishing a plan is a Core concern; Web only calls the plan endpoints.
- Resource conflict rules: conflicts are computed in Core; Web renders the advisory warnings it receives.
- Plan state transitions beyond calling `CoreClient.create_plan` / `update_plan` / `cancel_plan`.
- Reconciliation logic.
- Usage accounting.
- Beszel, psutil, or nvitop adapters.
- Direct database access (no SQLAlchemy, no persistence imports).

## Allowed dependencies

- Public core HTTP/API contracts (`labserver_contracts`) via `CoreClient`, the only Web-to-Core integration point.
- Shared schema/types from `packages/contracts` where appropriate.
- UI-only libraries with a documented reason (HTMX 2.0.x is vendored; see `apps/web/NOTICE`).

## Daily workflow

1. Read `docs/CURRENT_STATE.md` and this file.
2. Confirm required API/contract already exists before inventing UI-only semantics.
3. Test UI behavior using fake Core clients; never depend on lab hosts for development.
4. Keep labels for planned/observed/estimated data explicit: the schedule speaks of "Planned use" and "Overlap warning".

## UI invariants

- A host may be partially available: distinguish `fresh`, `stale`, `unavailable`, and unsupported capabilities.
- Do not expose full process command lines to ordinary members.
- Conflicts are advisory in V1 and must explain the resource/time overlap; they never block publishing a plan.
- An unplanned activity is an observation, not automatically a policy violation.
- Server cards use logical server names; real IPs are not rendered by default.
- Do not render approval, queue, priority, or allocation vocabulary as product concepts.

## Testing

Prefer route/view/component tests for all behavior and a small number of browser tests for critical flows:
- publish planned use;
- cancel planned use;
- schedule rendering;
- conflict-warning rendering;
- running-state freshness/error rendering (future milestone).

Web tests use a fake `CoreClient` (dependency override of `get_core_client`) and never require a running Core service.
