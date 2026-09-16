# M1.1H Web Correctness Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the merged M1.1 shared schedule so member-visible planning, advisory capacity warnings, timezone handling, filters, edit/cancel controls, and Web error paths match the approved product semantics before Docker/Beszel deployment work begins.

**Architecture:** Keep `PlanEntry` and the existing Core/Web split intact. Make the smallest Core corrections needed by the shared schedule, add explicit Web timezone and viewer-context boundaries, keep Core as the authorization/domain source of truth, and normalize Web-to-Core failures at `CoreClient`. No production auth transport or deployment is introduced.

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
│   ├── auth.py
│   ├── config.py
│   ├── time.py
│   ├── clients/core.py
│   ├── routes/schedule.py
│   └── templates/
│       ├── schedule/index.html
│       ├── schedule/_form.html
│       ├── schedule/_plans.html
│       └── schedule/edit.html
└── tests/
    ├── conftest.py
    ├── test_schedule.py
    ├── test_schedule_auth.py
    ├── test_schedule_errors.py
    └── test_time.py

services/core/
├── src/labserver_core/
│   ├── application/user_service.py
│   └── domain/conflicts.py
└── tests/
    ├── unit/test_authorization.py
    ├── unit/test_plan_conflicts.py
    ├── api/test_users.py
    └── api/test_plans.py

docs/
├── adr/0001-simple-planning-model.md
├── api/core-v1.md
├── HARNESS_ARCHITECTURE.md
├── harnesses/core.md
├── harnesses/web.md
└── CURRENT_STATE.md
```

Do not create a generic `utils.py`; timezone and auth boundaries stay named and focused.

---

### Task 1: Make the planning user directory member-readable

**Files:**
- Modify: `services/core/src/labserver_core/application/user_service.py`
- Modify: `services/core/tests/unit/test_authorization.py`
- Modify: `services/core/tests/api/test_users.py`

**Interfaces:**
- `UserService.list_users(actor: CurrentActor) -> list[User]` accepts any active persisted member/admin.
- `UserService.create_user(actor, data)` remains admin-only.
- Disabled, unknown, or role-mismatched actors remain rejected by `require_active_actor`.

- [ ] **Step 1: Write the failing service test**

Add to `services/core/tests/unit/test_authorization.py`:

```python
def test_active_member_can_list_users() -> None:
    uow = make_uow()
    service = UserService(
        factory_for(uow),
        clock=fixed_clock,
        id_factory=fixed_user_id_factory,
    )
    member = CurrentActor(MEMBER_ID, UserRole.MEMBER)

    users = service.list_users(member)

    assert {user.username for user in users} == {"admin", "member"}
```

Do not remove the existing admin create/list coverage.

- [ ] **Step 2: Rewrite the API permission test so list is member-readable but create is not**

Replace the current admin-only list assertion in `services/core/tests/api/test_users.py` with:

```python
def test_member_can_list_users_but_cannot_create(api_context: ApiContext) -> None:
    api_context.act_as(MEMBER_ID, UserRole.MEMBER)

    listed = api_context.client.get("/api/v1/users")
    created = api_context.client.post(
        "/api/v1/users",
        json={"username": "blocked", "display_name": "Blocked", "role": "member"},
    )

    assert listed.status_code == 200
    assert {item["username"] for item in listed.json()} == {"admin", "member", "other"}
    assert created.status_code == 403
    assert created.json()["error"]["code"] == "forbidden"
```

- [ ] **Step 3: Run RED**

```bash
uv run pytest services/core/tests/unit/test_authorization.py services/core/tests/api/test_users.py -q
```

Expected: the member list assertions fail with `Forbidden`/HTTP 403 under the current implementation.

- [ ] **Step 4: Implement the minimal service change**

In `UserService.list_users()`, keep:

```python
require_active_actor(actor, uow.users.get(actor.user_id))
return uow.users.list_all()
```

Remove only the `require_admin(actor)` call from the list operation. Leave `create_user()` unchanged.

- [ ] **Step 5: Verify**

```bash
uv run pytest services/core/tests/unit/test_authorization.py services/core/tests/api/test_users.py -q
uv run ruff check services/core/src/labserver_core/application/user_service.py services/core/tests/unit/test_authorization.py services/core/tests/api/test_users.py
uv run mypy services/core/src
```

- [ ] **Step 6: Commit**

```bash
git add services/core/src/labserver_core/application/user_service.py services/core/tests/unit/test_authorization.py services/core/tests/api/test_users.py
git commit -m "fix: expose planning user directory to members"
```

---

### Task 2: Warn when one plan alone exceeds known capacity

**Files:**
- Modify: `services/core/src/labserver_core/domain/conflicts.py`
- Modify: `services/core/tests/unit/test_plan_conflicts.py`
- Modify: `services/core/tests/api/test_plans.py`

**Interfaces:**
- `evaluate_plan_conflicts(candidate, existing, capacity) -> tuple[Conflict, ...]` keeps its signature.
- Candidate-alone CPU/RAM/GPU over-capacity warnings use `conflicting_plan_ids=()`.
- Explicit GPU device IDs outside a known `0..gpu_count-1` range produce confirmed `GPU_DEVICE` warnings with no conflicting plan IDs.
- Unknown capacity produces no fabricated capacity warning.

- [ ] **Step 1: Add RED unit tests**

Append these cases to `test_plan_conflicts.py`:

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


def test_candidate_alone_memory_over_capacity_warns() -> None:
    candidate = plan(start_at=dt(10), end_at=dt(12), memory_gb=384.0)

    conflicts = evaluate_plan_conflicts(candidate, [], capacity(memory_gb=256.0))

    assert {item.resource for item in conflicts} == {ConflictResource.MEMORY}


def test_explicit_gpu_id_outside_known_range_warns() -> None:
    candidate = plan(start_at=dt(10), end_at=dt(12), gpu_count=1, gpu_ids=(7,))

    conflicts = evaluate_plan_conflicts(candidate, [], capacity(gpu_count=4))
    device = next(item for item in conflicts if item.resource is ConflictResource.GPU_DEVICE)

    assert device.requested == (7,)
    assert device.available == (0, 1, 2, 3)
    assert device.conflicting_plan_ids == ()


def test_candidate_alone_unknown_capacity_does_not_warn() -> None:
    candidate = plan(
        start_at=dt(10),
        end_at=dt(12),
        cpu_cores=96,
        memory_gb=384.0,
        gpu_count=6,
    )

    conflicts = evaluate_plan_conflicts(
        candidate,
        [],
        capacity(cpu_cores=None, memory_gb=None, gpu_count=None),
    )

    assert conflicts == ()
```

- [ ] **Step 2: Run RED**

```bash
uv run pytest services/core/tests/unit/test_plan_conflicts.py -q
```

Expected: candidate-alone over-capacity tests fail because the current engine returns early when no existing plan overlaps.

- [ ] **Step 3: Evaluate the candidate interval even when no existing plan overlaps**

Remove the `if not relevant: return ()` shortcut. Always initialize segment boundaries with:

```python
boundaries = {candidate.start_at, candidate.end_at}
```

Add overlap boundaries from `relevant`, then run the existing segment loop. Allow `active` to be empty; aggregate checks must still use zero existing usage:

```python
existing_cpu = float(sum(plan.cpu_cores or 0 for plan in cpu_consumers))
existing_memory = float(sum(plan.memory_gb or 0.0 for plan in memory_consumers))
existing_gpu = float(sum(_declared_gpu_count(plan) for plan in gpu_consumers))
```

Do not skip the segment solely because `active` is empty.

- [ ] **Step 4: Add an explicit invalid-device helper**

Add a helper with this behavior:

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

Append that warning once per candidate, not once per overlap segment.

- [ ] **Step 5: Add API proof that the warning remains advisory**

In `services/core/tests/api/test_plans.py`, add a test that posts `gpu_count=5` to the existing 4-GPU test server, asserts HTTP 201, then fetches `/conflicts` and asserts a confirmed `gpu` warning with an empty `conflicting_plan_ids` list.

- [ ] **Step 6: Verify**

```bash
uv run pytest services/core/tests/unit/test_plan_conflicts.py services/core/tests/api/test_plans.py -q
uv run ruff check services/core/src/labserver_core/domain/conflicts.py services/core/tests/unit/test_plan_conflicts.py services/core/tests/api/test_plans.py
uv run mypy services/core/src/labserver_core/domain
```

- [ ] **Step 7: Commit**

```bash
git add services/core/src/labserver_core/domain/conflicts.py services/core/tests/unit/test_plan_conflicts.py services/core/tests/api/test_plans.py
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
- `WebSettings` gains `timezone_name: str = "UTC"`.
- `get_zone(timezone_name: str) -> ZoneInfo` validates the configured zone.
- `parse_local_datetime(raw: str, zone: ZoneInfo) -> datetime` returns UTC-aware datetime.
- `local_day_bounds(day: date, zone: ZoneInfo) -> tuple[datetime, datetime]` returns UTC-aware bounds.
- `today_in_zone(now_utc: datetime, zone: ZoneInfo) -> date` resolves the local calendar day.
- `format_local_window(start_utc, end_utc, zone, selected_day) -> str` returns unambiguous local display text.

- [ ] **Step 1: Add the new setting and failing tests**

`apps/web/tests/test_time.py` must include:

```python
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from labserver_web.config import load_settings
from labserver_web.time import local_day_bounds, parse_local_datetime, today_in_zone


def test_parse_local_datetime_converts_to_utc() -> None:
    zone = ZoneInfo("Asia/Shanghai")

    parsed = parse_local_datetime("2026-09-20T14:00", zone)

    assert parsed == datetime(2026, 9, 20, 6, 0, tzinfo=UTC)


def test_local_day_bounds_are_utc() -> None:
    zone = ZoneInfo("Asia/Shanghai")

    start, end = local_day_bounds(date(2026, 9, 20), zone)

    assert start == datetime(2026, 9, 19, 16, 0, tzinfo=UTC)
    assert end == datetime(2026, 9, 20, 16, 0, tzinfo=UTC)


def test_today_in_zone_uses_local_calendar_day() -> None:
    zone = ZoneInfo("Asia/Shanghai")

    current = today_in_zone(datetime(2026, 9, 19, 17, 0, tzinfo=UTC), zone)

    assert current == date(2026, 9, 20)


def test_invalid_timezone_configuration_is_rejected() -> None:
    with pytest.raises(ValueError, match="Invalid LABSERVER_TIMEZONE"):
        load_settings({"LABSERVER_TIMEZONE": "Invalid/Timezone"})
```

- [ ] **Step 2: Run RED**

```bash
uv run pytest apps/web/tests/test_time.py -q
```

- [ ] **Step 3: Implement config validation**

`load_settings()` must read:

```text
LABSERVER_CORE_URL
LABSERVER_TIMEZONE
```

Validate the timezone during config load with `ZoneInfo`. Keep the existing loopback Core URL as the development-safe default and `UTC` as the timezone default. Do not silently fall back from an invalid zone.

- [ ] **Step 4: Implement pure timezone helpers**

Use this parsing rule:

```python
def parse_local_datetime(raw: str, zone: ZoneInfo) -> datetime:
    value = datetime.fromisoformat(raw)
    if value.tzinfo is not None:
        raise ValueError("datetime-local value must not include a timezone")
    return value.replace(tzinfo=zone).astimezone(UTC)
```

Use local midnight boundaries rather than adding 24 hours in UTC:

```python
def local_day_bounds(day: date, zone: ZoneInfo) -> tuple[datetime, datetime]:
    start_local = datetime.combine(day, time.min, tzinfo=zone)
    end_local = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)
```

`format_local_window()` must convert both UTC timestamps to the configured zone. If both local timestamps fall on the selected day, return `HH:MM–HH:MM`; otherwise include `MM-DD HH:MM` on the boundary that falls outside the selected day.

- [ ] **Step 5: Update Web test settings**

Change the shared Web test settings fixture to use `timezone_name="Asia/Shanghai"` so schedule tests prove local/UTC conversion instead of accidentally passing under UTC.

- [ ] **Step 6: Verify**

```bash
uv run pytest apps/web/tests/test_time.py -q
uv run ruff check apps/web/src/labserver_web/config.py apps/web/src/labserver_web/time.py apps/web/tests/test_time.py apps/web/tests/conftest.py
uv run mypy apps/web/src
```

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/labserver_web/config.py apps/web/src/labserver_web/time.py apps/web/tests/test_time.py apps/web/tests/conftest.py
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
- `/schedule` query parameters are `server`, `owner`, and `date`.
- `server` is the logical server key.
- `owner` is a UUID string from the member-readable user directory.
- omitted `date` resolves to today in the configured timezone.
- Core receives UTC day bounds through existing `start`/`end` plan filters.

- [ ] **Step 1: Add focused failing tests**

Add tests with these concrete assertions:

```python
def test_server_filter_renders_only_selected_group(
    client: TestClient,
    fake_core: FakeCoreClient,
) -> None:
    response = client.get("/schedule", params={"server": "fwq10", "date": "2026-09-20"})

    assert response.status_code == 200
    assert "fwq10" in response.text
    assert "fwq51" not in response.text


def test_unknown_server_filter_returns_422(client: TestClient) -> None:
    response = client.get("/schedule", params={"server": "missing", "date": "2026-09-20"})

    assert response.status_code == 422


def test_owner_filter_reaches_core(
    client: TestClient,
    fake_core: FakeCoreClient,
) -> None:
    response = client.get(
        "/schedule",
        params={"owner": str(ALICE_ID), "date": "2026-09-20"},
    )

    assert response.status_code == 200
    list_calls = [payload for name, payload in fake_core.calls if name == "list_plans"]
    assert list_calls[-1]["owner_id"] == ALICE_ID
```

Also add tests for unknown owner 422, rendered timezone label, default local date, and a cross-day plan window containing a date marker.

- [ ] **Step 2: Run RED**

```bash
uv run pytest apps/web/tests/test_schedule.py -q
```

- [ ] **Step 3: Refactor schedule context resolution**

Resolve lookup maps before querying plans:

```python
servers = {item.key: item for item in core.list_servers()}
users = {user.id: user for user in core.list_users()}
```

Unknown filters must raise 422:

```python
if server_key is not None and server_key not in servers:
    raise HTTPException(status_code=422, detail=f"Unknown server key: {server_key}")

if owner_id is not None and owner_id not in users:
    raise HTTPException(status_code=422, detail=f"Unknown owner: {owner_id}")
```

Resolve the selected local day, get UTC bounds from `local_day_bounds()`, and call Core with `server_id`, `owner_id`, `start`, and `end`.

When `server` is selected, build one group only. Without a server filter, build all registered server groups.

- [ ] **Step 4: Update the filter UI**

Add owner dropdown and timezone label to `schedule/index.html`. Keep the page server-rendered; do not add a calendar dependency.

- [ ] **Step 5: Replace direct UTC `_time()` rendering**

Use `format_local_window()` from Task 3 for every displayed plan. Remove the helper that forces UTC `strftime("%H:%M")`.

- [ ] **Step 6: Verify**

```bash
uv run pytest apps/web/tests/test_schedule.py apps/web/tests/test_time.py -q
uv run ruff check apps/web/src/labserver_web/routes/schedule.py apps/web/src/labserver_web/templates apps/web/tests/test_schedule.py
uv run mypy apps/web/src
```

- [ ] **Step 7: Commit**

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
- Modify: `apps/web/src/labserver_web/templates/schedule/_form.html`
- Modify: `apps/web/tests/conftest.py`
- Create: `apps/web/tests/test_schedule_auth.py`

**Interfaces:**
- `ViewerContext(user_id: UUID, role: UserRole)` is presentation identity only.
- `get_current_viewer() -> ViewerContext` is default-deny and always raises HTTP 401 until a future auth adapter overrides it.
- `can_mutate(viewer, plan) -> bool` is a UX helper only; Core remains authoritative.

- [ ] **Step 1: Create the default-deny auth boundary**

Implement `auth.py` exactly around this shape:

```python
from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException
from labserver_contracts.common import UserRole


@dataclass(frozen=True, slots=True)
class ViewerContext:
    user_id: UUID
    role: UserRole


def get_current_viewer() -> ViewerContext:
    raise HTTPException(status_code=401, detail="Authentication adapter is not configured")
```

Do not inspect headers, cookies, or query parameters.

- [ ] **Step 2: Refactor Web test fixtures to support explicit viewer overrides**

In `apps/web/tests/conftest.py`, expose an `app` fixture, then build `client` from it. The standard `client` fixture should override `get_current_viewer` with Alice as a member so existing schedule behavior tests remain authenticated. Add an `anonymous_client` fixture that leaves the viewer dependency untouched.

Use:

```python
app.dependency_overrides[get_current_viewer] = lambda: ViewerContext(
    user_id=ALICE_ID,
    role=UserRole.MEMBER,
)
```

- [ ] **Step 3: Add failing auth/presentation tests**

Create `test_schedule_auth.py` with tests that prove:

```python
def test_schedule_is_default_deny_without_viewer(anonymous_client: TestClient) -> None:
    response = anonymous_client.get("/schedule")
    assert response.status_code == 401
```

For a plan owned by Alice, assert owner response contains both `/edit` and `/cancel` action URLs. Override the viewer to Bob and assert both URLs are absent. Override viewer role to admin and assert both URLs are present for Alice's plan.

- [ ] **Step 4: Pass ViewerContext through schedule routes**

Add a FastAPI dependency alias for `ViewerContext`. `_schedule_context()` must compute:

```python
can_change = viewer.role is UserRole.ADMIN or viewer.user_id == plan.owner_id
```

Store this boolean in each row. `_plans.html` renders Edit and Cancel only when `row.can_change` is true.

- [ ] **Step 5: Add the edit flow**

Add:

```text
GET  /schedule/{plan_id}/edit
POST /schedule/{plan_id}/edit
```

GET loads the plan through `CoreClient.get_plan()`. If the viewer is neither owner nor admin, return 403 before rendering the form. POST builds a `PlanUpdate` using Task 3 timezone parsing, calls `CoreClient.update_plan()`, and redirects with HTTP 303 on success.

Reuse `_form.html` only if it remains readable; otherwise keep create and edit templates separate rather than introducing conditional-template complexity.

- [ ] **Step 6: Add edit translation tests**

Submit `start_at="2026-09-20T14:00"` under `Asia/Shanghai` and assert the fake Core receives `2026-09-20T06:00:00+00:00`. Assert another member gets HTTP 403 from the edit route even when calling it directly.

- [ ] **Step 7: Verify**

```bash
uv run pytest apps/web/tests/test_schedule_auth.py apps/web/tests/test_schedule.py apps/web/tests/test_time.py -q
uv run ruff check apps/web/src apps/web/tests
uv run mypy apps/web/src
```

- [ ] **Step 8: Commit**

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
- `CoreClientError` remains the normalized HTTP-error carrier.
- Add `CoreUnavailableError(CoreClientError)` with status 503 and code `service_unavailable`.
- `CoreClient._request()` catches `httpx.RequestError` and raises `CoreUnavailableError`.
- Route code catches local parsing/Pydantic errors and normalized Core errors only; it does not catch raw HTTPX exceptions.

- [ ] **Step 1: Normalize network failures in CoreClient**

Add:

```python
class CoreUnavailableError(CoreClientError):
    def __init__(self, message: str = "Core service is unavailable") -> None:
        super().__init__(503, "service_unavailable", message)
```

Wrap the transport call:

```python
try:
    response = self._client.request(method, path, **kwargs)
except httpx.RequestError as error:
    raise CoreUnavailableError() from error
```

Do not put the raw URL or exception repr into the user-visible message.

- [ ] **Step 2: Add concrete failing Web error tests**

Create `test_schedule_errors.py`. Use a valid base form and mutate one field per test:

```python
BASE_FORM = {
    "title": "Assembly",
    "server_key": "fwq10",
    "date": "2026-09-20",
    "start_at": "2026-09-20T14:00",
    "end_at": "2026-09-20T18:00",
    "cpu_cores": "32",
    "memory_gb": "64",
    "gpu_count": "1",
    "gpu_ids": "0",
    "note": "shared",
}
```

Required cases:

```text
cpu_cores = "abc" -> 422
memory_gb = "abc" -> 422
gpu_ids = "0,x" -> 422
end_at earlier than start_at -> 422
gpu_count = "1" with gpu_ids = "0,1" -> 422
Core 403/404/409/422 on mutation -> same safe 4xx rendering
Core transport failure -> 503
cancel Core failure -> safe rendered/returned error, not traceback
```

Every response assertion must include:

```python
assert "traceback" not in response.text.lower()
```

- [ ] **Step 3: Centralize create/update form parsing**

Use `parse_local_datetime()` for form datetimes. Wrap conversion plus `PlanCreate`/`PlanUpdate` construction with:

```python
except (ValueError, ValidationError) as error:
```

Convert that into a rendered HTTP 422 form response with a short validation message. Preserve submitted values in the template context so a user does not have to retype the whole plan.

- [ ] **Step 4: Render normalized Core errors**

Use these status rules:

```text
Core 401 -> 401
Core 403 -> 403
Core 404 -> 404
Core 409 -> 409
Core 422 -> 422
Core 5xx -> 503
Core transport failure -> 503
```

Create a focused helper that maps `CoreClientError` into a safe template context and status code. Do not expose raw response bodies.

- [ ] **Step 5: Cover schedule-read failures**

When `list_servers`, `list_users`, `list_plans`, or conflict lookups fail through `CoreClient`, render a clear unavailable/error response. A Core outage must not surface an unhandled exception page.

- [ ] **Step 6: Verify**

```bash
uv run pytest apps/web/tests/test_schedule_errors.py apps/web/tests -q
uv run ruff check apps/web/src apps/web/tests
uv run mypy apps/web/src
```

- [ ] **Step 7: Commit**

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
- Modify: `docs/harnesses/core.md`
- Modify: `docs/CURRENT_STATE.md`
- Keep: `docs/adr/0001-simple-planning-model.md`
- Keep: `docs/superpowers/specs/2026-09-16-m1-1h-web-hardening-design.md`
- Keep: `docs/superpowers/plans/2026-09-16-m1-1h-web-hardening.md`
- Modify: `services/core/tests/test_architecture_boundaries.py`

**Documentation requirements:**
- Core API docs describe the actual server endpoints; remove the false `PATCH /api/v1/servers/{id}` claim instead of expanding scope.
- `GET /api/v1/users` documents member/admin read access; `POST /api/v1/users` remains admin-only.
- Web schedule docs describe configured local timezone behavior and the default-deny ViewerContext seam.
- Active harness docs no longer describe `TaskRequest`, `Reservation`, or approval transitions as current ownership.
- Historical specs/plans keep old wording for provenance.

- [ ] **Step 1: Update current API and harness documentation after code is green**

`docs/api/core-v1.md` must match actual routes. `docs/HARNESS_ARCHITECTURE.md` must describe Web as owning plan forms/schedule presentation and Core as owning `PlanEntry`, conflicts, runtime reconciliation, and reporting. Remove active approval-transition ownership language.

- [ ] **Step 2: Add a Web architecture boundary guard**

Extend `services/core/tests/test_architecture_boundaries.py` so every Python file under `apps/web/src` is scanned and fails if it imports a module whose root is `labserver_core` or `sqlalchemy`.

Use the existing AST scanner pattern rather than regex-import parsing.

- [ ] **Step 3: Update CURRENT_STATE with actual implementation branch and head**

Immediately before the final docs commit, run:

```bash
git branch --show-current
git rev-parse HEAD
```

Copy those exact outputs into `docs/CURRENT_STATE.md`. Record that M1.1 main baseline is `a2ce4a924cb017c3730fa393dc9f78d6fb882407` with merged-main CI run `35036877089` success. State that M1.1H is under review and not deployed. Do not describe M1.1H as merged until main actually contains it.

- [ ] **Step 4: Run targeted guard verification**

```bash
uv run pytest services/core/tests/test_architecture_boundaries.py -q
uv run ruff check .
```

- [ ] **Step 5: Run the full repository gate**

```bash
uv sync --all-packages --dev --locked
uv run ruff check .
uv run mypy services/core/src packages/contracts/src apps/web/src
uv run pytest -q
```

Also verify all of these explicitly:

```text
fresh empty SQLite upgrades to Alembic head
M1 0001 SQLite upgrades to current head
Core /healthz smoke passes
Plan API smoke passes
Web /schedule smoke passes with test ViewerContext override
secret/private-infrastructure scan is clear
active approval-terminology scan is clear
```

Do not deploy anything.

- [ ] **Step 6: Inspect the final diff against the M1.1H spec**

The final diff must satisfy every item below:

```text
no Docker/Beszel/Runtime Collector files
no auth header/query identity bypass
no real hostname/IP/token/credential
PlanEntry remains published intent only
capacity warnings remain advisory
member user directory works
Web uses configured timezone
owner/admin mutation controls only
invalid form/Core/network failures do not become uncaught 500s
```

- [ ] **Step 7: Commit final docs/state**

```bash
git add docs services/core/tests/test_architecture_boundaries.py
git commit -m "docs: finalize M1.1H hardening state"
```

- [ ] **Step 8: Push and open/update the PR**

The PR description must include the exact base SHA, exact final HEAD SHA, Task 1-7 completion status, pytest count/result, Ruff result, mypy result, migration smoke result, Web smoke result, architecture guard result, secret/private-infra scan result, and the explicit statement `NOT DEPLOYED`.

Do not merge merely because PR CI is green. Review the exact final head, then merge, then verify merged-main CI before marking M1.1H complete.