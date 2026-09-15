# M1.1 Simple Planning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> This plan is executor-agnostic. No AI-agent workflow is required; a human engineer can execute the same task/test/commit sequence directly.

**Goal:** Replace the pre-deployment request/approval/reservation workflow with one lightweight `PlanEntry` model and a simple shared `/schedule` web page that communicates intended server/GPU use without locking, approving, dispatching, or enforcing resources.

**Architecture:** Preserve the existing contracts/core/persistence boundaries from M1, replace only the request/reservation vertical slice with a plan slice, and add the first minimal `web` harness as a separate FastAPI/Jinja2 presentation service. Core remains the source of planning truth; Web calls Core over HTTP and never implements conflict logic. Human authentication transport remains default-deny and is not bypassed for production in this milestone.

**Tech Stack:** Python 3.13; uv workspace; FastAPI 0.141.1; Pydantic 2.13.5; SQLAlchemy 2.0.52; Alembic 1.20.0; SQLite; HTTPX 0.28.1; Jinja2 3.1.x; HTMX 2.0.x vendored as a static asset; pytest 9.1.1; Ruff 0.16.7; mypy 2.3.1.

**Spec:** `docs/superpowers/specs/2026-09-15-m1-1-simple-planning-design.md`

## Global Constraints

- Planning means only: “I intend to use this server/resource during this time window.”
- There is no draft/submitted/approved/rejected workflow, approval queue, resource lock, queue position, priority, dispatch, or enforcement.
- Conflicts and capacity problems are advisory warnings only; they do not block create/update.
- `PlanEntry` is the only public planning concept after M1.1.
- Time intervals use half-open semantics `[start_at, end_at)`.
- `cpu_cores`, `memory_gb`, `gpu_count`, and `gpu_ids` are optional declarations; missing means “not declared,” not zero.
- Cancelled plans remain auditable but are excluded from normal schedule queries unless `include_cancelled=true`.
- Members may create plans and edit/cancel only their own; admins may edit/cancel any plan.
- Human authentication transport remains separate; production routes remain default-deny until a trusted adapter is configured. No temporary header/query-string admin bypass is allowed.
- No real server IPs, credentials, SSH material, usernames, tokens, or private command lines may enter Git.
- Server identity remains the stable database server ID/logical key; deployment endpoints remain runtime configuration.
- Core business logic remains framework-independent; routes do not import persistence/SQLAlchemy.
- Web does not access SQLite and does not reimplement plan validation/conflict logic.
- M1.1 does not add Docker/Beszel/Runtime Collector deployment; those are M2 concerns.
- M1.1 is pre-production. The migration must upgrade an M1 database, but no compatibility promise is required for unapproved/draft local development requests.

---

## File Structure Locked by This Plan

```text
LabServer/
├── pyproject.toml
├── packages/contracts/
│   ├── src/labserver_contracts/
│   │   ├── __init__.py
│   │   ├── common.py
│   │   ├── plans.py                  # new canonical planning DTOs
│   │   ├── servers.py
│   │   └── users.py
│   └── tests/
│       └── test_plans.py
├── services/core/
│   ├── migrations/versions/
│   │   ├── 0001_initial_core.py      # unchanged
│   │   └── 0002_simple_planning.py   # new
│   ├── src/labserver_core/
│   │   ├── domain/
│   │   │   ├── entities.py
│   │   │   └── conflicts.py
│   │   ├── application/
│   │   │   ├── ports.py
│   │   │   └── plan_service.py
│   │   ├── persistence/
│   │   │   ├── models.py
│   │   │   ├── repositories.py
│   │   │   └── unit_of_work.py
│   │   └── api/
│   │       ├── dependencies.py
│   │       ├── router.py
│   │       └── routes/plans.py
│   └── tests/
│       ├── unit/
│       │   ├── test_plan_conflicts.py
│       │   └── test_plan_service.py
│       ├── persistence/
│       │   └── test_migrations.py
│       └── api/
│           └── test_plans.py
├── apps/web/
│   ├── pyproject.toml
│   ├── src/labserver_web/
│   │   ├── __init__.py
│   │   ├── app.py
│   │   ├── config.py
│   │   ├── dependencies.py
│   │   ├── clients/core.py
│   │   ├── routes/schedule.py
│   │   ├── templates/base.html
│   │   ├── templates/schedule/index.html
│   │   ├── templates/schedule/_plans.html
│   │   ├── templates/schedule/_form.html
│   │   └── static/
│   │       ├── app.css
│   │       └── vendor/htmx-2.0.x.min.js
│   └── tests/
│       ├── conftest.py
│       └── test_schedule.py
└── docs/
    ├── api/core-v1.md
    ├── harnesses/{core,web}.md
    └── CURRENT_STATE.md
```

Files removed only after the replacement slice is green:

```text
packages/contracts/src/labserver_contracts/{requests,reservations}.py
services/core/src/labserver_core/application/{request_service,reservation_service}.py
services/core/src/labserver_core/domain/transitions.py
services/core/src/labserver_core/api/routes/{requests,reservations}.py
services/core/tests/unit/{test_request_service,test_transitions}.py
services/core/tests/api/{test_requests,test_approval}.py
services/core/tests/persistence/test_approval_transaction.py
```

---

### Task 1: Define the single planning contract

**Files:**
- Create: `packages/contracts/src/labserver_contracts/plans.py`
- Create: `packages/contracts/tests/test_plans.py`
- Modify: `packages/contracts/src/labserver_contracts/__init__.py`
- Modify later in Task 7: `packages/contracts/src/labserver_contracts/common.py`

**Interfaces:**
- Produces `PlanCreate`, `PlanUpdate`, `PlanRead`, `PlanDisplayState`, `PlanConflictRead`.
- Retains canonical `UserRole`, `ConflictCertainty`, `ConflictResource`, base read/write models, UTC validation, and error response types from `common.py`.
- `PlanCreate` fields: `server_id`, `title`, `project`, `start_at`, `end_at`, `cpu_cores`, `memory_gb`, `gpu_count`, `gpu_ids`, `note`.
- `PlanUpdate` contains the same mutable fields as optional values; ownership is never client-settable.
- `PlanRead` additionally contains `id`, `owner_id`, `cancelled_at`, `created_at`, `updated_at`, `display_state`.

- [ ] **Step 1: Write failing contract tests**

`packages/contracts/tests/test_plans.py` must cover UTC normalization, optional resources, invalid time windows, duplicate/negative GPU IDs, and GPU count/ID mismatch:

```python
from uuid import UUID

from pydantic import ValidationError

from labserver_contracts.plans import PlanCreate


def test_plan_create_allows_time_only_intent() -> None:
    plan = PlanCreate.model_validate(
        {
            "server_id": "00000000-0000-0000-0000-000000000010",
            "title": "Poplar assembly",
            "start_at": "2026-09-18T00:00:00Z",
            "end_at": "2026-09-20T00:00:00Z",
        }
    )
    assert plan.server_id == UUID("00000000-0000-0000-0000-000000000010")
    assert plan.gpu_count is None
    assert plan.cpu_cores is None


def test_plan_create_rejects_gpu_count_mismatch() -> None:
    with pytest.raises(ValidationError):
        PlanCreate.model_validate(
            {
                "server_id": "00000000-0000-0000-0000-000000000010",
                "title": "Training",
                "start_at": "2026-09-18T00:00:00Z",
                "end_at": "2026-09-18T06:00:00Z",
                "gpu_count": 1,
                "gpu_ids": [0, 1],
            }
        )
```

Also assert `end_at <= start_at` fails and naive datetimes fail.

- [ ] **Step 2: Run the new test to verify RED**

```bash
uv run pytest packages/contracts/tests/test_plans.py -q
```

Expected: import failure for `labserver_contracts.plans`.

- [ ] **Step 3: Implement the DTOs**

Use strict write models and a model validator equivalent to:

```python
@model_validator(mode="after")
def validate_plan(self) -> Self:
    if self.end_at <= self.start_at:
        raise ValueError("end_at must be after start_at")
    if self.gpu_ids is not None:
        if len(set(self.gpu_ids)) != len(self.gpu_ids):
            raise ValueError("gpu_ids must be unique")
        if any(device < 0 for device in self.gpu_ids):
            raise ValueError("gpu_ids must be non-negative")
        if self.gpu_count is not None and self.gpu_count != len(self.gpu_ids):
            raise ValueError("gpu_count must match gpu_ids")
    return self
```

Use the existing UTC-aware datetime validator rather than introducing a second implementation.

- [ ] **Step 4: Verify contracts**

```bash
uv run pytest packages/contracts/tests -q
uv run ruff check packages/contracts
uv run mypy packages/contracts/src
```

Expected: all exit `0`.

- [ ] **Step 5: Commit**

```bash
git add packages/contracts

git commit -m "feat: define simple planning contracts"
```

---

### Task 2: Replace planning domain semantics with `PlanEntry`

**Files:**
- Modify: `services/core/src/labserver_core/domain/entities.py`
- Modify: `services/core/src/labserver_core/domain/conflicts.py`
- Create: `services/core/tests/unit/test_plan_conflicts.py`

**Interfaces:**
- Produces immutable domain entity `PlanEntry` with the spec fields.
- Produces `plan_display_state(plan: PlanEntry, now: datetime) -> PlanDisplayState`.
- Produces `evaluate_plan_conflicts(candidate: PlanEntry, existing: Sequence[PlanEntry], capacity: ServerCapacity) -> tuple[Conflict, ...]`.
- Conflict evaluation ignores cancelled plans and plans on other servers.

- [ ] **Step 1: Write failing domain tests**

Create fixtures directly as domain dataclasses. At minimum:

```python
def test_adjacent_plans_do_not_overlap() -> None:
    first = plan(start_at=dt(10), end_at=dt(12), gpu_ids=(0,))
    second = plan(start_at=dt(12), end_at=dt(14), gpu_ids=(0,))
    assert evaluate_plan_conflicts(second, [first], capacity(gpu_count=4)) == ()


def test_explicit_same_gpu_overlap_warns() -> None:
    first = plan(start_at=dt(10), end_at=dt(13), gpu_ids=(0,))
    second = plan(start_at=dt(12), end_at=dt(14), gpu_ids=(0,))
    conflicts = evaluate_plan_conflicts(second, [first], capacity(gpu_count=4))
    assert {c.resource for c in conflicts} == {ConflictResource.GPU_DEVICE}
```

Also cover aggregate GPU oversubscription, mixed explicit/count-only uncertainty, CPU/memory oversubscription, missing resource declarations, cancelled entries, and derived `upcoming/ongoing/past/cancelled` display state.

- [ ] **Step 2: Run RED**

```bash
uv run pytest services/core/tests/unit/test_plan_conflicts.py -q
```

Expected: `PlanEntry` or new conflict API missing.

- [ ] **Step 3: Implement `PlanEntry` and adapt the existing conflict engine**

Do not create a second scheduling algorithm. Preserve the existing half-open interval and resource aggregation logic, changing its input from `Reservation` to `PlanEntry`. Missing optional quantities must be excluded from that resource sum rather than coerced to zero.

Derived state logic must be pure:

```python
def plan_display_state(plan: PlanEntry, now: datetime) -> PlanDisplayState:
    if plan.cancelled_at is not None:
        return PlanDisplayState.CANCELLED
    if now < plan.start_at:
        return PlanDisplayState.UPCOMING
    if now < plan.end_at:
        return PlanDisplayState.ONGOING
    return PlanDisplayState.PAST
```

- [ ] **Step 4: Verify domain tests**

```bash
uv run pytest services/core/tests/unit/test_plan_conflicts.py -q
uv run ruff check services/core/src/labserver_core/domain services/core/tests/unit/test_plan_conflicts.py
uv run mypy services/core/src/labserver_core/domain
```

- [ ] **Step 5: Commit**

```bash
git add services/core/src/labserver_core/domain services/core/tests/unit/test_plan_conflicts.py

git commit -m "refactor: simplify planning domain to plan entries"
```

---

### Task 3: Add the `plan_entries` schema and migrate M1 development data

**Files:**
- Create: `services/core/migrations/versions/0002_simple_planning.py`
- Modify: `services/core/src/labserver_core/persistence/models.py`
- Modify: `services/core/src/labserver_core/persistence/repositories.py`
- Modify: `services/core/src/labserver_core/persistence/unit_of_work.py`
- Modify: `services/core/src/labserver_core/application/ports.py`
- Modify: `services/core/tests/persistence/test_migrations.py`
- Add/modify repository tests under: `services/core/tests/persistence/`

**Interfaces:**
- Produces `PlanRepository` protocol with `get`, `add`, `list`, and `save` operations.
- `UnitOfWork.plans` exposes a read-only `PlanRepository` property, following the existing structural-typing pattern.
- SQLAlchemy repository maps ORM rows to/from domain `PlanEntry`; application code never receives ORM rows.

**Schema:**

```text
plan_entries
- id UUID/text PK
- owner_id FK users.id NOT NULL
- server_id FK managed_servers.id NOT NULL
- title text NOT NULL
- project text NULL
- start_at datetime NOT NULL
- end_at datetime NOT NULL
- cpu_cores integer NULL
- memory_gb float NULL
- gpu_count integer NULL
- gpu_ids JSON NULL
- note text NULL
- cancelled_at datetime NULL
- created_at datetime NOT NULL
- updated_at datetime NOT NULL
```

Indexes: `(server_id, start_at, end_at)`, `(owner_id, start_at)`, `cancelled_at` if query planning shows benefit; do not add speculative indexes beyond schedule filters.

- [ ] **Step 1: Extend migration tests first**

Test both paths:

```text
fresh database -> 0002 head
0001 database with one approved reservation -> 0002 head
```

For the populated path, seed one request + reservation using the 0001 schema and assert after upgrade:

```python
assert row["owner_id"] == old_reservation.owner_id
assert row["server_id"] == old_reservation.server_id
assert row["project"] == old_request.project
assert row["note"] == old_request.note
assert row["start_at"] == old_reservation.start_at
```

Assert final tables include `plan_entries` and exclude `task_requests` and `reservations`.

- [ ] **Step 2: Run RED**

```bash
uv run pytest services/core/tests/persistence/test_migrations.py -q
```

- [ ] **Step 3: Implement `0002_simple_planning.py`**

Migration order:

```text
1. create plan_entries
2. INSERT...SELECT reservations LEFT JOIN task_requests
3. map reservation status=cancelled to cancelled_at=reservation.updated_at
4. drop reservations
5. drop task_requests
```

Use the reservation UUID as the migrated plan UUID. Requests with no reservation are intentionally not converted because an unapproved development request did not represent published intended use under the clarified product semantics.

Do not edit `0001_initial_core.py`.

- [ ] **Step 4: Implement ORM/repository/UoW changes**

The repository list signature must support the public schedule filters:

```python
def list(
    self,
    *,
    server_id: UUID | None = None,
    owner_id: UUID | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    include_cancelled: bool = False,
) -> list[PlanEntry]: ...
```

Window semantics: return plans where `plan.start_at < query_end` and `plan.end_at > query_start`; do not require full containment.

- [ ] **Step 5: Verify persistence**

```bash
uv run pytest services/core/tests/persistence -q
uv run ruff check services/core/src/labserver_core/persistence services/core/migrations
uv run mypy services/core/src/labserver_core/persistence services/core/src/labserver_core/application/ports.py
```

- [ ] **Step 6: Commit**

```bash
git add services/core/migrations services/core/src/labserver_core/persistence services/core/src/labserver_core/application/ports.py services/core/tests/persistence

git commit -m "feat: persist simple plan entries"
```

---

### Task 4: Implement plan application service and authorization

**Files:**
- Create: `services/core/src/labserver_core/application/plan_service.py`
- Modify: `services/core/src/labserver_core/application/__init__.py`
- Create: `services/core/tests/unit/test_plan_service.py`
- Modify/remove obsolete authorization assertions in: `services/core/tests/unit/test_authorization.py`

**Interfaces:**
- `PlanService.create(actor, PlanCreate) -> PlanRead`
- `PlanService.get(actor, plan_id) -> PlanRead`
- `PlanService.list(actor, filters...) -> list[PlanRead]`
- `PlanService.update(actor, plan_id, PlanUpdate) -> PlanRead`
- `PlanService.cancel(actor, plan_id) -> PlanRead`
- `PlanService.conflicts(actor, plan_id) -> list[PlanConflictRead]`

- [ ] **Step 1: Write failing service tests**

At minimum:

```python
def test_member_can_update_own_plan() -> None: ...
def test_member_cannot_update_another_members_plan() -> None: ...
def test_admin_can_update_any_plan() -> None: ...
def test_cancel_is_idempotent() -> None: ...
def test_cancelled_plans_are_excluded_from_default_list() -> None: ...
def test_create_returns_warnings_but_does_not_block_overlap() -> None: ...
```

Use fake repositories/UoW; no SQLAlchemy in these tests.

- [ ] **Step 2: Run RED**

```bash
uv run pytest services/core/tests/unit/test_plan_service.py -q
```

- [ ] **Step 3: Implement service**

Create path:

```text
require active actor
-> require enabled target server
-> build PlanEntry(owner_id=actor.user_id)
-> evaluate advisory capacity/conflicts
-> add plan + audit event
-> commit once
```

Update path:

```text
load plan
-> member must own; admin may edit any
-> merge partial fields
-> validate final start/end/resource shape
-> evaluate warnings
-> save plan + audit event
-> commit once
```

Cancel path sets `cancelled_at` once. Repeated cancel returns the already-cancelled plan without creating duplicate state transitions; audit behavior must be deterministic and tested.

Do not persist display state or conflict rows.

- [ ] **Step 4: Verify service layer**

```bash
uv run pytest services/core/tests/unit/test_plan_service.py services/core/tests/unit/test_plan_conflicts.py -q
uv run ruff check services/core/src/labserver_core/application services/core/tests/unit
uv run mypy services/core/src/labserver_core/application
```

- [ ] **Step 5: Commit**

```bash
git add services/core/src/labserver_core/application services/core/tests/unit

git commit -m "feat: add simple plan application service"
```

---

### Task 5: Replace request/reservation HTTP surface with `/api/v1/plans`

**Files:**
- Create: `services/core/src/labserver_core/api/routes/plans.py`
- Modify: `services/core/src/labserver_core/api/dependencies.py`
- Modify: `services/core/src/labserver_core/api/router.py`
- Create: `services/core/tests/api/test_plans.py`
- Modify: `services/core/tests/api/conftest.py`
- Remove in Task 7 after this task is green: old request/reservation routes/tests

**Interfaces:**

```text
GET    /api/v1/plans
POST   /api/v1/plans
GET    /api/v1/plans/{plan_id}
PATCH  /api/v1/plans/{plan_id}
POST   /api/v1/plans/{plan_id}/cancel
GET    /api/v1/plans/{plan_id}/conflicts
```

List query parameters:

```text
server_id: UUID | null
owner_id: UUID | null
start: aware datetime | null
end: aware datetime | null
include_cancelled: bool = false
```

- [ ] **Step 1: Write API tests first**

Cover 401 default-deny, 403 cross-owner update, create/get/list/update/cancel, idempotent cancel, 404, invalid interval 422, filters, cancelled exclusion, and conflict response shape.

Example:

```python
def test_plan_create_is_direct_publication(client_as_member, server_id) -> None:
    response = client_as_member.post(
        "/api/v1/plans",
        json={
            "server_id": str(server_id),
            "title": "RNA-seq",
            "start_at": "2026-09-20T01:00:00Z",
            "end_at": "2026-09-20T05:00:00Z",
            "gpu_count": 1,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert "status" not in body
    assert "approved" not in body
```

- [ ] **Step 2: Run RED**

```bash
uv run pytest services/core/tests/api/test_plans.py -q
```

- [ ] **Step 3: Implement thin route/dependency wiring**

Routes may parse HTTP inputs and map service results only. They must not import SQLAlchemy or persistence modules. Keep the existing stable error envelope and domain-to-HTTP mapping.

- [ ] **Step 4: Verify API + architecture guard**

```bash
uv run pytest services/core/tests/api/test_plans.py services/core/tests/test_architecture_boundaries.py -q
uv run ruff check services/core/src/labserver_core/api
uv run mypy services/core/src/labserver_core/api
```

- [ ] **Step 5: Commit**

```bash
git add services/core/src/labserver_core/api services/core/tests/api/test_plans.py services/core/tests/api/conftest.py

git commit -m "feat: expose plan API"
```

---

### Task 6: Add the minimal Schedule web harness

**Files:**
- Create: `apps/web/pyproject.toml`
- Create: `apps/web/src/labserver_web/__init__.py`
- Create: `apps/web/src/labserver_web/config.py`
- Create: `apps/web/src/labserver_web/app.py`
- Create: `apps/web/src/labserver_web/dependencies.py`
- Create: `apps/web/src/labserver_web/clients/core.py`
- Create: `apps/web/src/labserver_web/routes/schedule.py`
- Create: `apps/web/src/labserver_web/templates/base.html`
- Create: `apps/web/src/labserver_web/templates/schedule/index.html`
- Create: `apps/web/src/labserver_web/templates/schedule/_plans.html`
- Create: `apps/web/src/labserver_web/templates/schedule/_form.html`
- Create: `apps/web/src/labserver_web/static/app.css`
- Vendor: `apps/web/src/labserver_web/static/vendor/htmx-2.0.x.min.js`
- Create: `apps/web/tests/conftest.py`
- Create: `apps/web/tests/test_schedule.py`
- Modify: root `pyproject.toml`
- Regenerate: `uv.lock`

**Interfaces:**
- `CoreClient` is the only Web-to-Core integration point.
- `CoreClient.list_plans(...)`, `create_plan(...)`, `update_plan(...)`, `cancel_plan(...)` speak HTTP using `labserver_contracts.plans` DTOs.
- Route dependency `get_core_client()` is overrideable in tests.
- Web has no SQLAlchemy/database imports.

- [ ] **Step 1: Add Web package to the workspace and test paths**

Root workspace must become:

```toml
[tool.uv.workspace]
members = ["packages/contracts", "services/core", "apps/web"]
```

Add `apps/web/tests` to pytest testpaths. `apps/web/pyproject.toml` dependencies:

```toml
[project]
name = "labserver-web"
version = "0.1.0"
requires-python = ">=3.13,<3.14"
dependencies = [
  "fastapi==0.141.1",
  "httpx==0.28.1",
  "jinja2>=3.1,<3.2",
  "labserver-contracts",
  "pydantic==2.13.5",
  "uvicorn==0.52.4",
]
```

Use workspace source for `labserver-contracts`. No Node/npm dependencies.

- [ ] **Step 2: Write failing schedule tests with a fake Core client**

Tests must never require a running Core service. Cover:

```python
def test_schedule_renders_plans(client, fake_core) -> None: ...
def test_schedule_empty_state(client, fake_core) -> None: ...
def test_schedule_filters_server_and_date(client, fake_core) -> None: ...
def test_schedule_marks_overlap_warning(client, fake_core) -> None: ...
def test_schedule_form_uses_planned_use_language(client) -> None: ...
def test_schedule_does_not_render_approval_language(client) -> None: ...
```

Also test POST form translation to `PlanCreate` and cancel action translation to `CoreClient.cancel_plan`.

- [ ] **Step 3: Run RED**

```bash
uv run pytest apps/web/tests/test_schedule.py -q
```

- [ ] **Step 4: Implement the minimal page**

`/schedule` is server-rendered and intentionally simple:

```text
Schedule
[date] [server]

Server A
09:00–13:00  Alice  RNA-seq     GPU 0     [Overlap warning]
14:00–18:00  Bob    Assembly    32 CPU

[Add planned use]
```

Use wording `Schedule`, `Planned use`, and `Overlap warning`. Do not render `approved`, `reservation`, `queue`, `priority`, or `allocation` as product concepts.

Do not add calendar JavaScript libraries in M1.1. A grouped chronological list is sufficient; a graphical calendar can be added only if usage proves it necessary.

- [ ] **Step 5: Vendor HTMX without introducing a JS build system**

Use an official HTMX 2.0.x release asset, commit the minified file under `static/vendor/`, and record its upstream version/license in a short comment in `apps/web/pyproject.toml` or adjacent `NOTICE` file. Runtime pages must not depend on a CDN.

- [ ] **Step 6: Verify Web**

```bash
uv lock
uv sync --all-packages --dev --locked
uv run pytest apps/web/tests -q
uv run ruff check apps/web
uv run mypy apps/web/src
```

Expected: all exit `0`.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock apps/web

git commit -m "feat: add simple shared schedule web"
```

---

### Task 7: Remove obsolete approval/reservation slice and enforce the simplified architecture

**Files:**
- Remove: `packages/contracts/src/labserver_contracts/requests.py`
- Remove: `packages/contracts/src/labserver_contracts/reservations.py`
- Modify: `packages/contracts/src/labserver_contracts/common.py`
- Modify: `packages/contracts/src/labserver_contracts/__init__.py`
- Remove: `services/core/src/labserver_core/application/request_service.py`
- Remove: `services/core/src/labserver_core/application/reservation_service.py`
- Remove: `services/core/src/labserver_core/domain/transitions.py`
- Remove: `services/core/src/labserver_core/api/routes/requests.py`
- Remove: `services/core/src/labserver_core/api/routes/reservations.py`
- Remove obsolete tests listed in the file-structure section
- Modify: `services/core/tests/test_architecture_boundaries.py`
- Add a repository-wide terminology guard test or focused source scan test.

**Interfaces:**
- After this task there is no importable public `TaskRequest`, `Reservation`, `TaskRequestStatus`, `ReservationStatus`, or `ReservationSource` planning API.
- `ConflictResource`/`ConflictCertainty` remain only if used by plan conflicts.

- [ ] **Step 1: Add a failing terminology/source guard**

The guard scans product code and templates, excluding migration `0001`, migration `0002` migration-copy SQL, historical specs/plans, and test fixtures that intentionally assert absence. It must fail if active product code imports or exposes:

```text
TaskRequest
Reservation
TaskRequestStatus
ReservationStatus
approve
reject
/api/v1/requests
/api/v1/reservations
```

Do not ban the English word `reservation` from historical docs/migrations globally; scope the guard to active product source and current API docs.

- [ ] **Step 2: Run guard to verify RED**

```bash
uv run pytest services/core/tests/test_architecture_boundaries.py -q
```

Expected: old active files are reported.

- [ ] **Step 3: Delete old slice and clean exports/enums/router wiring**

Delete only after Tasks 1–6 are green. Preserve user/server/audit code, stable errors, health endpoint, and M1 migration `0001`.

- [ ] **Step 4: Run full tests and static checks**

```bash
uv run ruff check .
uv run mypy services/core/src packages/contracts/src apps/web/src
uv run pytest -q
```

Expected: all exit `0`, with no tests referring to approval as current product behavior.

- [ ] **Step 5: Commit**

```bash
git add -A

git commit -m "refactor: remove approval-based planning workflow"
```

---

### Task 8: Update current docs and run the M1.1 merge gate

**Files:**
- Modify: `docs/api/core-v1.md`
- Modify: `docs/harnesses/core.md`
- Modify: `docs/harnesses/web.md`
- Modify: `docs/PROJECT_KNOWLEDGE.md` only where the old request/approval semantics are stated as durable facts
- Modify: `README.md` if it describes approval/reservation as the current product
- Modify: `docs/CURRENT_STATE.md`
- Modify: `.github/workflows/ci.yml` only if needed to include Web mypy explicitly

**Interfaces / documentation truth:**
- Planning is a shared declaration, not approval or resource reservation.
- Current API documents only `/plans` planning endpoints.
- M2 boundary is Docker-first deployment + Beszel primary monitoring + minimal Runtime Collector + Running view.

- [ ] **Step 1: Update API/harness docs**

`docs/api/core-v1.md` must document the six plan endpoints, ownership rules, advisory conflicts, filters, cancellation semantics, and default-deny auth boundary. Remove current request/approval/reservation endpoint documentation.

`docs/harnesses/web.md` must state that `/schedule` is presentation only and uses Core API contracts; no conflict logic lives in Web.

- [ ] **Step 2: Update `CURRENT_STATE.md` only after code is complete**

Record:

```text
M1.1 implemented: PlanEntry + /api/v1/plans + /schedule
old request/approval/reservation product slice removed
not deployed
next gate: review + CI + merge, then M2 Docker/Beszel design finalization
```

Do not claim deployed or production-ready human authentication.

- [ ] **Step 3: Verify a fresh empty database migration**

From repository root, using a temporary SQLite path:

```bash
rm -f /tmp/labserver-m11-smoke.sqlite
LABSERVER_DATABASE_URL=sqlite:////tmp/labserver-m11-smoke.sqlite \
  uv run --package labserver-core alembic -c services/core/alembic.ini upgrade head
```

Inspect schema and assert final tables include:

```text
alembic_version
audit_events
managed_servers
plan_entries
users
```

and exclude:

```text
task_requests
reservations
```

- [ ] **Step 4: Verify the M1 -> M1.1 upgrade path**

Create a temporary DB at revision `0001`, seed one request+reservation using test-safe synthetic data, upgrade to `head`, and run the migration assertion test:

```bash
uv run pytest services/core/tests/persistence/test_migrations.py -q
```

- [ ] **Step 5: Run the full local merge gate**

```bash
uv sync --all-packages --dev --locked
uv run ruff check .
uv run mypy services/core/src packages/contracts/src apps/web/src
uv run pytest -q
```

All commands must exit `0`.

- [ ] **Step 6: Run a public-repository secret/private-infrastructure scan**

At minimum scan the diff for real RFC1918 IPs, tokens, keys, usernames, `.env` values, SSH material, and private command lines. TEST-NET addresses may appear only in explicit validation tests.

- [ ] **Step 7: Verify remote CI on the final PR head**

The final GitHub Actions run must be bound to the exact final head SHA and complete successfully for locked sync, Ruff, mypy, and pytest before merge.

- [ ] **Step 8: Commit documentation/status**

```bash
git add README.md docs .github/workflows/ci.yml

git commit -m "docs: finalize simple planning milestone"
```

---

## M1.1 Acceptance Checklist

- [ ] One public planning concept: `PlanEntry`.
- [ ] No active approval/rejection/request/reservation workflow remains.
- [ ] `/api/v1/plans` create/get/list/update/cancel/conflicts works with stable errors.
- [ ] `/schedule` renders a simple shared planned-use view.
- [ ] GPU/CPU/memory declarations are optional.
- [ ] Conflicts are advisory and do not block publication.
- [ ] Members can edit/cancel only their own plans; admins can correct any plan.
- [ ] Cancelled plans are excluded by default and retained for audit.
- [ ] Fresh DB -> head migration succeeds.
- [ ] M1 `0001` DB -> M1.1 head migration succeeds.
- [ ] Old request/reservation tables are absent at head.
- [ ] Core/Web harness boundaries remain enforced.
- [ ] No production auth bypass is introduced.
- [ ] No private infrastructure data or secrets are committed.
- [ ] Ruff, mypy, pytest, and final GitHub Actions CI all pass.
- [ ] No deployment is performed in M1.1.

## Explicit Deferred Work

Do not pull these into M1.1:

- Docker/Compose deployment.
- Beszel Hub/Agent integration.
- Runtime Collector.
- Running page.
- Dashboard host metrics.
- plan-vs-actual reconciliation.
- GPU-hour/CPU-hour statistics.
- SSE/WebSocket.
- Redis/PostgreSQL.
- remote shell/process kill/job submission.
- graphical calendar libraries unless the simple schedule proves inadequate.
