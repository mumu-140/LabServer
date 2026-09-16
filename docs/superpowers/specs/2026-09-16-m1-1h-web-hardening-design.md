# M1.1H Web Correctness Hardening Design

Date: 2026-09-16
Status: Approved

## 1. Purpose

M1.1 successfully replaced the approval/reservation model with lightweight `PlanEntry` published intent and was squash-merged to `main` as `a2ce4a924cb017c3730fa393dc9f78d6fb882407`. Merged-main CI run `35036877089` passed locked sync, Ruff, mypy, and 97 tests.

Post-merge review found several correctness and documentation gaps that should be fixed before Docker/Beszel deployment work begins. M1.1H is a narrow hardening milestone. It does not redesign the domain and does not introduce a new product capability.

## 2. In scope

M1.1H fixes the following:

1. Web schedule timezone semantics.
2. Web schedule filtering/grouping/date presentation.
3. Web form validation and Core-error rendering so user input cannot produce unhandled 500s.
4. Owner/admin-aware edit and cancel controls without introducing a production authentication bypass.
5. Member-readable planning user directory so a normal member can render owner names and filter the shared schedule.
6. Advisory capacity warnings when one plan by itself exceeds known server capacity, including impossible explicit GPU indices.
7. Missing cross-harness ADR and stale API/current-state documentation.

## 3. Explicitly out of scope

M1.1H does not add:

- a production login mechanism;
- cookies, sessions, OAuth/OIDC, LDAP, SSO, or trusted-proxy authentication;
- header/query-string identity bypasses;
- Docker Compose;
- deployment to the current central host or any compute node;
- Beszel;
- Runtime Collector;
- Running/Dashboard views;
- scheduler behavior;
- workload execution, SSH, kill, renice, or job submission;
- a frontend framework or Node build chain.

Human-auth transport remains an M2 deployment concern. M1.1H only makes the Web's identity boundary explicit and default-deny.

## 4. Core planning semantics remain unchanged

`PlanEntry` remains the only public planning concept.

- publishing is immediate;
- conflicts are advisory;
- resources are never locked;
- missing CPU/RAM/GPU fields mean `not declared`;
- `[start_at, end_at)` remains the canonical time interval;
- cancellation remains idempotent;
- Core remains the authorization source of truth.

No request/approval/reservation lifecycle may return.

## 5. Planning user directory

The shared schedule must display who owns each plan and allow filtering by user. Current Web calls `GET /api/v1/users`, while `UserService.list_users()` is admin-only. This makes a member-visible schedule impossible even after authentication is introduced.

Decision:

- `GET /api/v1/users` becomes readable by any active authenticated member/admin;
- `POST /api/v1/users` remains admin-only;
- no new directory subsystem is introduced in M1.1H;
- the existing `UserRead` response remains the contract for now because this is an internal lab system and the user registry already stores only planning identity metadata;
- disabled users may remain visible for attribution of historical plans; mutation rules are unchanged.

This is intentionally the smallest design that makes the approved shared schedule work.

## 6. Capacity warning semantics

Known capacity is advisory metadata, not an admission gate.

The current conflict engine evaluates candidate capacity only when an overlapping existing plan creates a segment. Therefore a single plan requesting, for example, 6 GPUs on a 4-GPU server can incorrectly report no warning.

M1.1H changes conflict evaluation so the candidate's entire interval is always evaluated against known capacity, even when there are no overlapping plans.

Examples:

```text
server gpu_count = 4
candidate gpu_count = 6
=> confirmed GPU capacity warning
=> conflicting_plan_ids = ()
=> publication remains allowed
```

```text
server cpu_cores = 64
candidate cpu_cores = 96
=> confirmed CPU capacity warning
=> publication remains allowed
```

```text
server gpu_count = 4
candidate gpu_ids = (7,)
=> confirmed GPU_DEVICE warning because device 7 cannot exist under the declared capacity
=> publication remains allowed
```

Unknown capacity continues to produce no aggregate-capacity claim.

## 7. Web timezone contract

HTML `datetime-local` values do not contain a timezone. They must never be silently interpreted as UTC.

Add Web setting:

```text
LABSERVER_TIMEZONE=<IANA timezone name>
```

Rules:

- development-safe default: `UTC`;
- implementation uses Python standard-library `zoneinfo.ZoneInfo`; no new timezone dependency;
- a `datetime-local` form value is interpreted in `LABSERVER_TIMEZONE`, then converted to UTC before creating/updating a Core DTO;
- timestamps returned by Core remain UTC-aware and are converted back to `LABSERVER_TIMEZONE` for display;
- the selected schedule day is a local calendar day in `LABSERVER_TIMEZONE`;
- local day start/end are converted to UTC before sending `start`/`end` filters to Core;
- the page visibly labels the configured timezone;
- invalid timezone configuration fails application startup/config loading clearly rather than silently falling back.

Do not hard-code a lab location or machine hostname into source control.

## 8. Schedule query and display behavior

The `/schedule` page is a day-oriented coordination view.

Default behavior:

- if `date` is omitted, select today's date in `LABSERVER_TIMEZONE`;
- always query one local-day window;
- show only the selected server group when a server filter is active;
- unknown server filter => Web 422, never silently fall back to all servers;
- add user/owner filter using the existing Core `owner_id` plan filter;
- unknown owner filter => Web 422;
- retain simple list/table presentation; do not add a calendar package.

Time rendering:

- show local `HH:MM` for plans fully contained in the selected local day;
- if a plan crosses the selected-day boundary, include a concise date marker so the displayed interval is unambiguous;
- timezone name/abbreviation must be visible near the schedule filter/header.

## 9. Web identity boundary and controls

M1.1H must not invent production authentication, but the Web cannot continue rendering mutation controls for every plan.

Introduce a Web presentation identity boundary:

```python
@dataclass(frozen=True, slots=True)
class ViewerContext:
    user_id: UUID
    role: UserRole
```

and dependency:

```python
def get_current_viewer(...) -> ViewerContext:
    raise HTTPException(status_code=401, detail="Authentication adapter is not configured")
```

Rules:

- this dependency is default-deny;
- tests may override it exactly as Core tests override `get_current_actor`;
- no request header/query parameter is parsed as identity in M1.1H;
- the future M2 auth adapter will supply ViewerContext and authenticated Core credentials;
- Web route checks are UX checks only; Core remains the final authorization boundary.

Template behavior:

- create form: authenticated viewer only;
- edit control: owner or admin only;
- cancel control: owner or admin only;
- other users' plans remain visible but have no mutation controls;
- admin can edit/cancel any plan.

## 10. Edit flow

Add a minimal server-rendered edit flow; do not build an SPA.

Recommended routes:

```text
GET  /schedule/{plan_id}/edit
POST /schedule/{plan_id}/edit
```

The edit form may reuse a focused form partial but must submit `PlanUpdate` through `CoreClient.update_plan()`.

The Web must not duplicate domain validation or authorization rules. It may parse form syntax and provide early user-friendly errors; Core remains authoritative.

## 11. Error handling

Current form parsing can raise `ValueError` / Pydantic `ValidationError` before Core is called. These must become stable Web responses rather than 500s.

Create/update form handling must catch and render:

- malformed integer/float values;
- malformed GPU ID lists;
- malformed local datetimes;
- end <= start contract validation;
- GPU count/ID mismatch;
- Core 401/403/404/409/422;
- Core 5xx/unavailable errors.

Behavior:

- local form/contract validation: render form with HTTP 422 and preserve submitted values where practical;
- Core 4xx: render a clear action error with the corresponding 4xx status;
- Core 5xx/network failures: render a service-unavailable state, normally HTTP 503;
- cancel errors must not become uncaught exceptions;
- schedule page read failure must render a clear unavailable/error page rather than raw traceback.

## 12. Web/Core client boundary

Keep `CoreClient` as the only Web-to-Core integration point.

- Web templates never access Core directly;
- Web never accesses SQLite;
- `CoreClient` continues to use canonical DTOs;
- network errors from HTTPX are normalized into a Web/Core-client error type so routes do not depend on raw HTTPX exception classes;
- M1.1H does not add real authentication headers because the production auth transport is still deferred.

## 13. Documentation corrections

Before M1.1H is considered complete:

- `docs/CURRENT_STATE.md` must record M1.1 as merged on exact main SHA `a2ce4a924cb017c3730fa393dc9f78d6fb882407` and merged-main CI run `35036877089` success;
- this M1.1H plan/branch must be recorded as not yet implemented/deployed until code actually lands;
- `docs/api/core-v1.md` must not claim a server PATCH route unless the HTTP route actually exists; M1.1H should document the actual surface rather than add unrelated server-management API scope;
- `docs/HARNESS_ARCHITECTURE.md` must remove active ownership language that still treats `TaskRequest` / `Reservation` / approval transitions as current concepts;
- ADR 0001 records the cross-harness simple-planning decision.

## 14. Tests

Minimum new coverage:

### Core

- member may list users;
- disabled/unknown actor still rejected as before;
- user creation remains admin-only;
- candidate-alone CPU over capacity warns;
- candidate-alone memory over capacity warns;
- candidate-alone GPU count over capacity warns;
- explicit GPU ID outside declared device range warns;
- unknown capacity does not fabricate a warning;
- warnings remain non-blocking.

### Web timezone

- configured IANA timezone parses `datetime-local` correctly to UTC;
- UTC Core timestamp renders back in configured local timezone;
- local day boundaries convert correctly to UTC;
- default day uses configured local timezone;
- invalid timezone config fails deterministically.

### Web schedule

- server filter renders only selected server group;
- unknown server => 422;
- owner filter reaches Core `owner_id`;
- unknown owner => 422;
- date/time display is unambiguous;
- timezone label is rendered.

### Web authorization/presentation

- owner sees edit/cancel;
- another member sees neither;
- admin sees edit/cancel for any plan;
- default viewer dependency is 401/default-deny;
- edit submits `PlanUpdate` to Core client.

### Web errors

- malformed integer/float/GPU IDs => rendered 422, not 500;
- invalid interval => rendered 422;
- Core 403/404/409/422 are rendered without traceback;
- Core network/5xx => 503/unavailable state;
- cancel Core error is handled.

## 15. Definition of done

M1.1H is complete only when:

- all issues above are covered by tests and implementation;
- M1.1 planning semantics remain unchanged;
- no real infrastructure values or credentials are committed;
- no auth bypass is introduced;
- full locked sync, Ruff, mypy, pytest, migration smoke, Web smoke, architecture guards, and private-infra/secret scan pass;
- final PR head CI is green;
- after merge, merged-main CI is green;
- no deployment has occurred.

Only then should M2 Docker + Beszel + Runtime Collector + production auth/deployment design proceed.