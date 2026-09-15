# Web Harness Guide

Scope: `apps/web/`

## Owns

- Dashboard, Servers, Running, Requests, Schedule, Statistics UI.
- Form handling and presentation validation.
- Rendering current-state updates from core APIs/SSE.
- Accessibility and responsive layout.

## Must not own

- Request state transitions.
- Resource conflict rules.
- Reconciliation logic.
- Usage accounting.
- Beszel, psutil, or nvitop adapters.
- Direct database access.

## Allowed dependencies

- Public core HTTP/API contracts.
- Shared schema/types from `packages/contracts` where appropriate.
- UI-only libraries with a documented reason.

## Daily workflow

1. Read `docs/CURRENT_STATE.md` and this file.
2. Confirm required API/contract already exists before inventing UI-only semantics.
3. Test UI behavior using fake/local API data; never depend on lab hosts for development.
4. Keep labels for planned/observed/estimated data explicit.

## UI invariants

- A host may be partially available: distinguish `fresh`, `stale`, `unavailable`, and unsupported capabilities.
- Do not expose full process command lines to ordinary members.
- Conflicts are advisory in V1 and must explain the resource/time overlap.
- An unplanned activity is an observation, not automatically a policy violation.
- Server cards use logical server names; real IPs are not rendered by default.

## Testing

Prefer route/view/component tests for all behavior and a small number of browser tests for critical flows:
- submit request;
- admin approval/rejection;
- conflict preview;
- schedule rendering;
- running-state freshness/error rendering.
