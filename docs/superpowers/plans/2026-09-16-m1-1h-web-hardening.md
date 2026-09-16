# M1.1H Web Correctness Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the merged M1.1 shared schedule so member-visible planning, advisory capacity warnings, timezone handling, filters, edit/cancel controls, and Web error paths match the approved product semantics before Docker/Beszel deployment work begins.

**Architecture:** Keep `PlanEntry` and the existing Core/Web split intact. Make the smallest Core corrections needed by the shared schedule, add explicit Web timezone and viewer-context boundaries, keep Core as the authorization/domain source of truth, and normalize all Web-to-Core failures at `CoreClient`. No production auth transport or deployment is introduced.

**Tech Stack:** Python 3.13; FastAPI 0.141.1; Pydantic 2.13.5; SQLAlchemy 2.0.52; Alembic 1.20.0; HTTPX 0.28.1; Jinja2 3.1.x; HTMX 2.0.4 vendored; standard-library `zoneinfo`; pytest 9.1.1; Ruff 0.16.7; mypy 2.3.1.

**Spec:** `docs/superpowers/specs/2026-09-16-m1-1h-web-hardening-design.md`

## Global Constraints

- M1.1H is hardening only; do not reintroduce request/approval/reservation lifecycle concepts.
- Conflicts/capacity remain advisory only and never block plan create/update.
- Core remains the final authorization/domain source of truth.
- Web remains a separate HTTP consumer; no SQLite or Core-internal imports from Web.
- No production authentication transport is implemented in this milestone.
- No header/query-string identity bypass is allowed.
- `LABSERVER_TIMEZONE` is an IANA timezone setting with development default `UTC`; use standard-library `zoneinfo`, not a new dependency.
- Database timestamps and Core contracts remain UTC-aware.
- No Docker, Beszel, Runtime Collector, Running/Dashboard, deployment, SSH, process control, or scheduler behavior.
- Repository is public: never commit real private IPs, credentials, tokens, usernames, SSH material, private command lines, or host-specific deployment values.
- Do not hard-code the current central deployment hostname in code/config/docs added by this milestone.

---

## File Structure Locked by This Plan

```text
apps/web/
├── src/labserver_web/
│   ├── auth.py                         # new default-deny ViewerContext boundary
│   ├── config.py                       # LABSERVER_TIMEZONE validation
│   ├── time.py                         # new local<->UTC helpers
│   ├── clients/core.py                 # normalize Core/network errors
│   ├── routes/schedule.py              # filters/create/edit/cancel/error rendering
│   └── templates/
│       ├── schedule/index.html
│       ├── schedule/_form.html
│       ├── schedule/_plans.html
│       └── schedule/edit.html           # new
└── tests/
    ├── conftest.py
    ├── test_schedule.py
    ├── test_schedule_auth.py            # new focused presentation-auth tests
    ├── test_schedule_errors.py          # new focused error tests
    └── test_time.py                     # new

services/core/
├── src/labserver_core/
│   ├── application/user_service.py
│   └── domain/conflicts.py
└── tests/
    ├── unit/test_authorization.py
    ├── unit/test_plan_conflicts.py
    └── api/test_plans.py

docs/
├── adr/0001-simple-planning-model.md
├── api/core-v1.md
├── HARNESS_ARCHITECTURE.md
└── CURRENT_STATE.md
```

Do not create a generic `utils.py`; timezone and auth boundaries stay named and focused.

---

### Task 1: Make the planning user directory member-readable

**Files:**
- Modify: `services/core/src/labserver_core/application/user_service.py`
- Modify: `services/core/tests/unit/test_authorization.py`
- Add/modify API coverage under: `services/core/tests/api/`

**Interfaces:**
- `UserService.list_users(actor: CurrentActor) -> list[User]` must accept any active persisted member/admin.
- `UserService.create_user(...)` remains admin-only.
- Disabled/unknown/mismatched actors remain rejected by existing `require_active_actor` behavior.

- [ ] **Step 1: Write failing service tests**

Add focused cases equivalent to:

```python
def test_active_member_can_list_users(context) -> None:
    service = UserService(context.uow_factory)
    users = service.list_users(context.member_actor)
    assert {user.id for user in users} >= {context.member.id, context.admin.id}


def test_member_still_cannot_create_user(context) -> None:
    service = UserService(context.uow_factory)
    with pytest.raises(Forbidden):
        service.create_user(context.member_actor, user_create("new-user"))
```

Also retain/verify disabled and unknown actor rejection.

- [ ] **Step 2: Run targeted tests and confirm RED**

```bash
uv run pytest services/core/tests/unit/test_authorization.py -q
```

Expected: member list test fails with `Forbidden` under current implementation.

- [ ] **Step 3: Make the minimal service change**

`list_users()` should keep:

```python
require_active_actor(actor, uow.users.get(actor.user_id))
```

and remove only the `require_admin(actor)` call from the list operation. Do not relax `create_user()`.

- [ ] **Step 4: Add HTTP proof**

Add an API test proving an authenticated member receives `200` from `GET /api/v1/users` while member `POST /api/v1/users` remains `403`.

- [ ] **Step 5: Verify**

```bash
uv run pytest services/core/tests/unit/test_authorization.py services/core/tests/api -q
uv run ruff check services/core/src/labserver_core/application/user_service.py services/core/tests
uv run mypy services/core/src
```

- [ ] **Step 6: Commit**

```bash
git add services/core/src/labserver_core/application/user_service.py services/core/tests
git commit -m "fix: expose planning user directory to members"
```

---

### Task 2: Warn when one plan alone exceeds known capacity

**Files:**
- Modify: `services/core/src/labserver_core/domain/conflicts.py`
- Modify: `services/core/tests/unit/test_plan_conflicts.py`
- Modify if needed: `services/core/tests/api/test_plans.py`

**Interfaces:**
- `evaluate_plan_conflicts(candidate, existing, capacity) -> tuple[Conflict, ...]` keeps the same signature.
- Candidate-alone CPU/RAM/GPU over-capacity warnings use `conflicting_plan_ids=()`.
- Explicit GPU device IDs outside a known `0..gpu_count-1` range produce a confirmed `GPU_DEVICE` warning with no conflicting plan IDs.
- Unknown capacity produces no fabricated capacity warning.

- [ ] **Step 1: Add RED tests**

Add cases equivalent to:

```python
def test_candidate_alone_gpu_over_capacity_warns() -> None:
    candidate = plan(start_at=dt(10), end_at=dt(12), gpu_count=6)
    conflicts = evaluate_plan_conflicts(candidate, [], capacity(gpu_count=4))
    gpu = next(item for item in conflicts if item.resource is ConflictResource.GPU)
    assert gpu.requested == 6.0
    assert gpu.available == 4.0
    assert gpu.conflicting_plan_ids == ()


def test_candidate_alone_cpu_over_capacity_warns() -> None:
    candidate = plan(start_at=dt(10), end_at=dt(12), cpu_cores=96)
    conflicts = evaluate_plan_conflicts(candidate, [], capacity(cpu_cores=64))
    assert {item.resource for item in conflicts} == {ConflictResource.CPU}


def test_explicit_gpu_id_outside_known_range_warns() -> None:
    candidate = plan(start_at=dt(10), end_at=dt(12), gpu_count=1, gpu_ids=(7,))
    conflicts = evaluate_plan_conflicts(candidate, [], capacity(gpu_count=4))
    device = next(item for item in conflicts if item.resource is ConflictResource.GPU_DEVICE)
    assert device.requested == (7,)
    assert device.available == (0, 1, 2, 3)
    assert device.conflicting_plan_ids == ()
```

Add the same pattern for memory and an unknown-capacity no-warning test.

- [ ] **Step 2: Run RED**

```bash
uv run pytest services/core/tests/unit/test_plan_conflicts.py -q
```

Expected: candidate-alone tests fail because current code returns early when no overlapping existing plan exists.

- [ ] **Step 3: Refactor segment evaluation without changing public semantics**

Remove the `if not relevant: return ()` shortcut. Build boundaries from the candidate interval plus relevant overlap boundaries and evaluate candidate capacity even when `active == []`.

The aggregate check should still compute:

```python
existing_requested = sum(...active declared quantities...)
available = capacity - existing_requested
```

so a candidate by itself can exceed the known capacity.

Add a focused helper for impossible explicit GPU IDs, for example:

```python
def _invalid_candidate_gpu_devices(
    candidate: PlanEntry,
    capacity: ServerCapacity,
) -> Conflict | None:
    if candidate.gpu_ids is None or capacity.gpu_count is None:
        return None
    valid = tuple(range(capacity.gpu_count))
    invalid = tuple(sorted(device for device in candidate.gpu_ids if device >= capacity.gpu_count))
    if not invalid:
        return None
    return Conflict(
        resource=ConflictResource.GPU_DEVICE,
        certainty=ConflictCertainty.CONFIRMED,
        start_at=candidate.start_at,
        end_at=candidate.end_at,
        requested=invalid,
        available=valid,
        conflicting_plan_ids=(),
        reason="Explicit GPU device plan references device(s) outside declared server capacity",
    )
```

Do not convert this warning into a create/update rejection.

- [ ] **Step 4: Add API proof that warning is non-blocking**

Create a plan whose declared GPU count exceeds known capacity and assert `POST /api/v1/plans` still returns `201`; then assert `/conflicts` returns the advisory capacity warning.

- [ ] **Step 5: Verify**

```bash
uv run pytest services/core/tests/unit/test_plan_conflicts.py services/core/tests/api/test_plans.py -q
uv run ruff check services/core/src/labserver_core/domain/conflicts.py services/core/tests
uv run mypy services/core/src/labserver_core/domain
```

- [ ] **Step 6: Commit**

```bash
git add services/core/src/labserver_core/domain/conflicts.py services/core/tests
git commit -m "fix: warn on standalone capacity overcommit"
```

---

### Task 3: Introduce explicit Web timezone semantics

**Files:**
- Modify: `apps/web/src/labserver_web/config.py`
- Create: `apps/web/src/labserver_web/time.py`
- Create: `apps/web/tests/test_time.py`
- Modify: `apps/web/tests/conftest.py`

**Interfaces:**

`WebSettings` becomes:

```python
@dataclass(frozen=True, slots=True)
class WebSettings:
    core_base_url: str = DEFAULT_CORE_BASE_URL
    timezone_name: str = "UTC"
```

`time.py` must expose focused helpers:

```python
def get_zone(timezone_name: str) -> ZoneInfo: ...
def parse_local_datetime(raw: str, zone: ZoneInfo) -> datetime: ...  # returns UTC
def local_day_bounds(day: date, zone: ZoneInfo) -> tuple[datetime, datetime]: ...  # UTC bounds
def today_in_zone(now_utc: datetime, zone: ZoneInfo) -> date: ...
def format_local_window(start_utc: datetime, end_utc: datetime, zone: ZoneInfo, selected_day: date) -> str: ...
```

- [ ] **Step 1: Write timezone RED tests**

Use a non-UTC IANA timezone in tests to prove conversion rather than accidentally passing under UTC. Example:

```python
def test_parse_local_datetime_converts_to_utc() -> None:
    zone = ZoneInfo("Asia/Shanghai")
    parsed = parse_local_datetime("2026-09-20T14:00", zone)
    assert parsed.isoformat() == "2026-09-20T06:00:00+00:00"
```

Also cover:

- UTC timestamp renders back as 14:00 local;
- local-day bounds cross to the correct UTC window;
- default day derives from configured timezone;
- invalid `LABSERVER_TIMEZONE` causes `load_settings()` to raise a clear configuration error.

- [ ] **Step 2: Run RED**

```bash
uv run pytest apps/web/tests/test_time.py -q
```

- [ ] **Step 3: Implement config validation with standard library only**

`load_settings()` must validate using `ZoneInfo(name)` and raise `ValueError` (or a small Web configuration exception) with the invalid timezone name. Do not silently fall back.

Read:

```text
LABSERVER_CORE_URL
LABSERVER_TIMEZONE
```

No hostname/IP default besides the existing loopback development Core URL.

- [ ] **Step 4: Implement pure timezone helpers**

`parse_local_datetime()` must reject any user-provided timezone suffix on the `datetime-local` input path if it would create ambiguous semantics; treat the HTML field as local wall time in the configured zone, attach that zone, and convert to UTC.

Do not use `.replace(tzinfo=UTC)` for a naive user-entered local time.

- [ ] **Step 5: Verify**

```bash
uv run pytest apps/web/tests/test_time.py -q
uv run ruff check apps/web/src/labserver_web/config.py apps/web/src/labserver_web/time.py apps/web/tests/test_time.py
uv run mypy apps/web/src
```

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/labserver_web/config.py apps/web/src/labserver_web/time.py apps/web/tests
git commit -m "fix: define schedule timezone semantics"
```

---

### Task 4: Fix schedule filters, grouping, and local-day rendering

**Files:**
- Modify: `apps/web/src/labserver_web/routes/schedule.py`
- Modify: `apps/web/src/labserver_web/templates/schedule/index.html`
- Modify: `apps/web/src/labserver_web/templates/schedule/_plans.html`
- Modify: `apps/web/tests/test_schedule.py`

**Interfaces:**
- `/schedule` query parameters: `server`, `owner`, `date`.
- `server` remains logical server key.
- `owner` is a UUID string backed by the member-readable user directory.
- omitted `date` resolves to today in configured timezone.
- Core receives UTC day bounds through existing `start`/`end` filters.

- [ ] **Step 1: Add RED tests for bad current behavior**

Cover all of:

```python
def test_server_filter_renders_only_selected_group(...): ...
def test_unknown_server_filter_returns_422(...): ...
def test_owner_filter_passes_owner_id_to_core(...): ...
def test_unknown_owner_filter_returns_422(...): ...
def test_default_date_is_today_in_configured_timezone(...): ...
def test_schedule_renders_timezone_label(...): ...
def test_cross_day_plan_has_unambiguous_window_text(...): ...
```

The first test must assert that a second unrelated server heading is absent, not just that Core received a server filter.

- [ ] **Step 2: Run RED**

```bash
uv run pytest apps/web/tests/test_schedule.py -q
```

- [ ] **Step 3: Refactor `_schedule_context`**

Resolve server and owner filters before Core plan query:

```python
servers = {item.key: item for item in core.list_servers()}
users = {user.id: user for user in core.list_users()}

if server_key and server_key not in servers:
    raise HTTPException(status_code=422, detail=f"Unknown server key: {server_key}")

if owner_id and owner_id not in users:
    raise HTTPException(status_code=422, detail=f"Unknown owner: {owner_id}")
```

Compute selected local day with helpers from Task 3, convert its bounds to UTC, and call:

```python
core.list_plans(
    server_id=selected_server.id if selected_server else None,
    owner_id=owner_id,
    start=start_utc,
    end=end_utc,
)
```

When filtered to one server, build exactly one group. Otherwise build groups for all registered servers.

- [ ] **Step 4: Update templates**

Add owner filter dropdown and visible timezone text. Do not add a calendar JS dependency.

Keep copy centered on:

- `Schedule`
- `Planned use`
- `Overlap warning`

- [ ] **Step 5: Verify**

```bash
uv run pytest apps/web/tests/test_schedule.py -q
uv run ruff check apps/web/src/labserver_web/routes/schedule.py apps/web/tests/test_schedule.py
uv run mypy apps/web/src
```

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/labserver_web/routes/schedule.py apps/web/src/labserver_web/templates apps/web/tests/test_schedule.py
git commit -m "fix: make schedule filters and dates deterministic"
```

---

### Task 5: Add default-deny Web viewer context and owner/admin edit controls

**Files:**
- Create: `apps/web/src/labserver_web/auth.py`
- Modify: `apps/web/src/labserver_web/routes/schedule.py`
- Modify: `apps/web/src/labserver_web/templates/schedule/_plans.html`
- Create: `apps/web/src/labserver_web/templates/schedule/edit.html`
- Modify or factor: `apps/web/src/labserver_web/templates/schedule/_form.html`
- Modify: `apps/web/tests/conftest.py`
- Create: `apps/web/tests/test_schedule_auth.py`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class ViewerContext:
    user_id: UUID
    role: UserRole


def get_current_viewer() -> ViewerContext:
    raise HTTPException(
        status_code=401,
        detail="Authentication adapter is not configured",
    )
```

Use `Annotated[ViewerContext, Depends(get_current_viewer)]` in schedule routes that need member context.

No headers/cookies/query parameters may become identity sources in M1.1H.

- [ ] **Step 1: Write RED tests for visibility and default deny**

Tests must override `get_current_viewer` with explicit `ViewerContext` fixtures.

Cover:

```python
def test_default_viewer_dependency_is_unauthorized(...): ...
def test_owner_sees_edit_and_cancel(...): ...
def test_other_member_sees_neither_edit_nor_cancel(...): ...
def test_admin_sees_edit_and_cancel_for_other_users_plan(...): ...
```

Do not rely only on button text; assert the relevant action URLs are absent/present.

- [ ] **Step 2: Run RED**

```bash
uv run pytest apps/web/tests/test_schedule_auth.py -q
```

- [ ] **Step 3: Implement ViewerContext boundary**

Add a small helper:

```python
def can_mutate(viewer: ViewerContext, plan: PlanRead) -> bool:
    return viewer.role is UserRole.ADMIN or viewer.user_id == plan.owner_id
```

Pass `can_mutate` as row presentation data. Do not treat this as security authorization; Core will still return 403 for unauthorized mutations.

- [ ] **Step 4: Add edit flow**

Add:

```text
GET  /schedule/{plan_id}/edit
POST /schedule/{plan_id}/edit
```

GET loads the plan through `CoreClient.get_plan()`, checks presentation permission, and renders `edit.html`.

POST builds `PlanUpdate` from form values using the timezone helper and calls:

```python
core.update_plan(plan_id, update)
```

After success, `303` back to `/schedule` while preserving useful `date/server/owner` query parameters when available.

- [ ] **Step 5: Add tests for edit translation**

Assert that local datetime values are converted to UTC before they reach the fake Core client and that an unauthorized member does not get a Web edit control. Core authorization tests remain the final security proof.

- [ ] **Step 6: Verify**

```bash
uv run pytest apps/web/tests/test_schedule_auth.py apps/web/tests/test_schedule.py -q
uv run ruff check apps/web/src apps/web/tests
uv run mypy apps/web/src
```

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/labserver_web/auth.py apps/web/src/labserver_web/routes/schedule.py apps/web/src/labserver_web/templates apps/web/tests
git commit -m "fix: add actor-aware schedule controls"
```

---

### Task 6: Normalize form and Core failures instead of returning 500

**Files:**
- Modify: `apps/web/src/labserver_web/clients/core.py`
- Modify: `apps/web/src/labserver_web/routes/schedule.py`
- Create: `apps/web/tests/test_schedule_errors.py`
- Modify: `apps/web/tests/conftest.py`

**Interfaces:**

Keep `CoreClientError`, but normalize network failures into it (or a subclass) inside `CoreClient._request()` so routes never catch raw HTTPX exceptions.

Recommended shape:

```python
class CoreUnavailableError(CoreClientError):
    def __init__(self, message: str = "Core service is unavailable") -> None:
        super().__init__(503, "service_unavailable", message)
```

`_request()` should catch `httpx.RequestError` and raise `CoreUnavailableError` from it.

- [ ] **Step 1: Write RED tests**

Cover:

- invalid integer CPU form input;
- invalid float memory input;
- malformed GPU ID list;
- end before start;
- GPU count/ID mismatch;
- Core 403 on edit/cancel;
- Core 404 on edit/cancel;
- Core 409/422 create/update response;
- HTTPX network failure becomes rendered 503;
- cancel failure is rendered/returned cleanly rather than uncaught.

Example assertion:

```python
response = client.post("/schedule", data=bad_form)
assert response.status_code == 422
assert "invalid" in response.text.lower()
assert "traceback" not in response.text.lower()
```

- [ ] **Step 2: Run RED**

```bash
uv run pytest apps/web/tests/test_schedule_errors.py -q
```

- [ ] **Step 3: Centralize form parsing**

Create focused parsing functions in `schedule.py` or a small named module if the route file would otherwise become unwieldy. Do not add generic helpers.

Catch:

```python
(ValueError, pydantic.ValidationError)
```

around local parsing/DTO construction and render HTTP 422 with submitted values preserved where practical.

- [ ] **Step 4: Normalize Core errors**

Map Core error responses to safe Web rendering:

```text
401/403/404/409/422 -> same status with readable action/form error
Core 5xx or network -> 503 unavailable state
```

Do not leak raw response bodies, stack traces, URLs containing credentials, or exception reprs into templates.

- [ ] **Step 5: Verify**

```bash
uv run pytest apps/web/tests/test_schedule_errors.py apps/web/tests -q
uv run ruff check apps/web/src apps/web/tests
uv run mypy apps/web/src
```

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/labserver_web/clients/core.py apps/web/src/labserver_web/routes/schedule.py apps/web/tests
git commit -m "fix: harden schedule error handling"
```

---

### Task 7: Correct architecture/API/state documentation and run the merge gate

**Files:**
- Modify: `docs/api/core-v1.md`
- Modify: `docs/HARNESS_ARCHITECTURE.md`
- Modify: `docs/harnesses/web.md`
- Modify if needed: `docs/harnesses/core.md`
- Modify: `docs/CURRENT_STATE.md`
- Keep: `docs/adr/0001-simple-planning-model.md`
- Keep: `docs/superpowers/specs/2026-09-16-m1-1h-web-hardening-design.md`
- Keep: `docs/superpowers/plans/2026-09-16-m1-1h-web-hardening.md`
- Modify guards/tests if required: `services/core/tests/test_architecture_boundaries.py`

**Documentation requirements:**

- Core API docs describe the actual server endpoints. Do not document `PATCH /api/v1/servers/{id}` unless an HTTP route is intentionally added in a separately approved scope; M1.1H should remove the false claim rather than expand scope.
- `GET /api/v1/users` documents member/admin read access; `POST /api/v1/users` remains admin-only.
- Web schedule docs state configured local timezone behavior and default-deny ViewerContext boundary.
- Active harness architecture no longer says Core owns current `TaskRequest` / `Reservation` lifecycle or Web owns approval transitions.
- Historical specs/plans may keep old terms for provenance.

- [ ] **Step 1: Update docs after code is green**

`CURRENT_STATE.md` should say, before merge:

```text
M1.1 merged to main as a2ce4a924cb017c3730fa393dc9f78d6fb882407.
Merged-main CI run 35036877089 succeeded.
M1.1H is implemented on <branch>/<head> and is under review.
Nothing has been deployed.
M2 Docker/Beszel work is blocked on M1.1H merge verification.
```

Do not claim M1.1H merged before it is actually merged.

- [ ] **Step 2: Strengthen terminology/architecture guards only where useful**

Keep historical docs excluded. Ensure active sources/current API docs do not reintroduce request/approval/reservation product semantics.

Add a Web boundary guard if absent that prevents imports from:

```text
labserver_core
sqlalchemy
labserver_core.persistence
```

inside `apps/web/src`.

- [ ] **Step 3: Run targeted documentation/guard tests**

```bash
uv run pytest services/core/tests/test_architecture_boundaries.py -q
uv run ruff check .
```

- [ ] **Step 4: Run full verification**

```bash
uv sync --all-packages --dev --locked
uv run ruff check .
uv run mypy services/core/src packages/contracts/src apps/web/src
uv run pytest -q
```

Also perform:

```text
fresh empty SQLite -> Alembic head
M1 0001 SQLite -> current head
Core /healthz smoke
Plan API smoke
Web /schedule smoke with test auth override
secret/private-infra scan
active approval-terminology scan
```

Do not deploy anything.

- [ ] **Step 5: Inspect the final diff against this spec**

Explicitly verify:

- no Docker/Beszel/Runtime Collector files were added;
- no auth header/query bypass was added;
- no hostname/IP/token/credential was committed;
- `PlanEntry` semantics remain published intent only;
- capacity warnings are advisory;
- Web uses configured timezone and member directory;
- only owner/admin mutation controls render;
- invalid form/Core failures no longer become uncaught 500s.

- [ ] **Step 6: Commit final docs/state**

```bash
git add docs services/core/tests/test_architecture_boundaries.py
git commit -m "docs: finalize M1.1H hardening state"
```

- [ ] **Step 7: Push and open/update PR**

PR description must include:

```text
base main SHA used
final HEAD SHA
Task 1-7 status
pytest count/result
Ruff result
mypy result
migration smoke result
Web smoke result
architecture guard result
secret/private-infra scan result
NOT DEPLOYED
```

Do not merge merely because PR CI is green. Review the exact final head first, then merge, then verify merged-main CI before marking M1.1H complete.