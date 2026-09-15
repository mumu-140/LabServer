# Milestone 1 Foundation + Core Planning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a testable central LabServer core that stores users, logical servers, task requests, reservations, performs request lifecycle/approval and advisory resource-conflict evaluation, and exposes versioned HTTP APIs without requiring any lab host, GPU, Beszel instance, or private-network access.

**Architecture:** Use a small Python monorepo workspace with an independent contracts package and a FastAPI core service. Business rules live in framework-independent domain/application modules; SQLAlchemy/Alembic are persistence adapters; HTTP routes are thin adapters. Authentication transport is intentionally not implemented in Milestone 1: API authorization consumes a `CurrentActor` dependency that is **default-deny in production** and overridden in tests, so no temporary insecure header-based auth is introduced.

**Tech Stack:** Python 3.13; uv workspace/lockfile; FastAPI 0.141.1; Pydantic 2.13.5; SQLAlchemy 2.0.52; Alembic 1.20.0; SQLite; pytest 9.1.1; Ruff 0.16.7; mypy 2.3.1; GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-15-labserver-design.md`

## Global Constraints

- V1 is observation + planning + reconciliation + reporting, **not** a scheduler.
- No real server IPs, credentials, SSH material, user secrets, or private command lines may enter Git.
- Server identity is a stable logical key such as `fwq10`; IP addresses are runtime configuration and are not database identity.
- Core tests must run without network access, Beszel, Linux process access, or a GPU.
- SQLite is the Milestone 1 database; foreign keys are enabled and migrations exist from the first schema.
- Timestamps are stored as UTC-aware datetimes.
- Task request and reservation are separate persisted concepts.
- Approval must create a reservation transactionally and be idempotent.
- Scheduling intervals are half-open: `[start, end)`.
- Conflicts are advisory in V1; conflict detection never dispatches, blocks, kills, or moves workloads.
- Business rules belong in `services/core/src/labserver_core/domain` or `application`, not in routes or ORM models.
- Shared API schemas/enums belong in `packages/contracts`; contracts contain no database access or service logic.
- HTTP authorization must default to deny until a real human-auth adapter is implemented in a later milestone.
- Python runtime baseline is 3.13. Do not adopt prerelease dependencies (for example SQLAlchemy 2.1 RC) in this milestone.

---

## File Structure Locked by This Plan

```text
LabServer/
├── pyproject.toml
├── uv.lock
├── .python-version
├── .github/
│   └── workflows/
│       └── ci.yml
├── packages/
│   └── contracts/
│       ├── pyproject.toml
│       ├── src/labserver_contracts/
│       │   ├── __init__.py
│       │   ├── common.py
│       │   ├── users.py
│       │   ├── servers.py
│       │   ├── requests.py
│       │   └── reservations.py
│       └── tests/
│           └── test_serialization.py
├── services/
│   └── core/
│       ├── pyproject.toml
│       ├── alembic.ini
│       ├── migrations/
│       │   ├── env.py
│       │   └── versions/
│       │       └── 0001_initial_core.py
│       ├── src/labserver_core/
│       │   ├── __init__.py
│       │   ├── app.py
│       │   ├── config.py
│       │   ├── api/
│       │   │   ├── dependencies.py
│       │   │   ├── errors.py
│       │   │   ├── router.py
│       │   │   └── routes/
│       │   │       ├── health.py
│       │   │       ├── users.py
│       │   │       ├── servers.py
│       │   │       ├── requests.py
│       │   │       └── reservations.py
│       │   ├── application/
│       │   │   ├── actors.py
│       │   │   ├── ports.py
│       │   │   ├── request_service.py
│       │   │   ├── reservation_service.py
│       │   │   └── server_service.py
│       │   ├── domain/
│       │   │   ├── entities.py
│       │   │   ├── enums.py
│       │   │   ├── errors.py
│       │   │   ├── transitions.py
│       │   │   └── conflicts.py
│       │   └── persistence/
│       │       ├── database.py
│       │       ├── models.py
│       │       ├── repositories.py
│       │       └── unit_of_work.py
│       └── tests/
│           ├── conftest.py
│           ├── unit/
│           │   ├── test_transitions.py
│           │   └── test_conflicts.py
│           ├── persistence/
│           │   └── test_migrations.py
│           └── api/
│               ├── test_health.py
│               ├── test_servers.py
│               ├── test_requests.py
│               └── test_approval.py
└── docs/
    └── api/
        └── core-v1.md
```

No `apps/web`, `services/agent`, Beszel adapter, SSE endpoint, or deployment-to-real-host file is added in Milestone 1.

---

### Task 1: Establish the Python workspace, dependency boundaries, and CI shell

**Files:**
- Create: `pyproject.toml`
- Create: `.python-version`
- Create: `packages/contracts/pyproject.toml`
- Create: `packages/contracts/src/labserver_contracts/__init__.py`
- Create: `services/core/pyproject.toml`
- Create: `services/core/src/labserver_core/__init__.py`
- Create: `.github/workflows/ci.yml`
- Generate/commit: `uv.lock`

**Interfaces:**
- Produces package import `labserver_contracts`.
- Produces package import `labserver_core`.
- Produces one workspace-level command surface: `uv run pytest`, `uv run ruff check .`, `uv run mypy ...`.

- [ ] **Step 1: Add workspace configuration with exact dependency lines**

Root `pyproject.toml`:

```toml
[project]
name = "labserver-workspace"
version = "0.0.0"
requires-python = ">=3.13,<3.14"

[tool.uv.workspace]
members = ["packages/contracts", "services/core"]

[dependency-groups]
dev = [
  "mypy==2.3.1",
  "pytest==9.1.1",
  "ruff==0.16.7",
]

[tool.pytest.ini_options]
addopts = "-ra"
testpaths = ["packages/contracts/tests", "services/core/tests"]

[tool.ruff]
target-version = "py313"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.mypy]
python_version = "3.13"
strict = true
warn_unused_configs = true
```

`packages/contracts/pyproject.toml`:

```toml
[project]
name = "labserver-contracts"
version = "0.1.0"
requires-python = ">=3.13,<3.14"
dependencies = ["pydantic==2.13.5"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

`services/core/pyproject.toml`:

```toml
[project]
name = "labserver-core"
version = "0.1.0"
requires-python = ">=3.13,<3.14"
dependencies = [
  "alembic==1.20.0",
  "fastapi==0.141.1",
  "labserver-contracts",
  "pydantic==2.13.5",
  "sqlalchemy==2.0.52",
  "uvicorn==0.35.0",
]

[tool.uv.sources]
labserver-contracts = { workspace = true }

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

`.python-version` contains exactly `3.13`.

- [ ] **Step 2: Generate the lockfile and verify imports**

Run:

```bash
uv lock
uv sync --all-packages --dev --locked
uv run python -c "import labserver_contracts, labserver_core"
```

Expected: all commands exit `0`.

- [ ] **Step 3: Add CI with no private-network dependency**

`.github/workflows/ci.yml` must run on `ubuntu-24.04`, Python 3.13, and execute:

```yaml
- run: uv sync --all-packages --dev --locked
- run: uv run ruff check .
- run: uv run mypy services/core/src packages/contracts/src
- run: uv run pytest -q
```

Do not define lab IPs, SSH secrets, VPN setup, or service containers.

- [ ] **Step 4: Run the empty-suite/tooling checks**

Run:

```bash
uv run ruff check .
uv run mypy services/core/src packages/contracts/src
uv run pytest -q
```

Expected: tooling succeeds; pytest may report no tests only until Task 2 adds the first tests.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .python-version uv.lock .github packages/contracts services/core
git commit -m "chore: establish Python workspace and CI"
```

---

### Task 2: Define stable shared contracts and domain enums

**Files:**
- Create: `packages/contracts/src/labserver_contracts/common.py`
- Create: `packages/contracts/src/labserver_contracts/users.py`
- Create: `packages/contracts/src/labserver_contracts/servers.py`
- Create: `packages/contracts/src/labserver_contracts/requests.py`
- Create: `packages/contracts/src/labserver_contracts/reservations.py`
- Modify: `packages/contracts/src/labserver_contracts/__init__.py`
- Create: `packages/contracts/tests/test_serialization.py`
- Create: `services/core/src/labserver_core/domain/enums.py`

**Interfaces:**
- Produces enums: `UserRole`, `TaskRequestStatus`, `ReservationStatus`, `ReservationSource`, `ConflictCertainty`, `ConflictResource`.
- Produces API DTOs: `UserRead`, `ServerRead`, `TaskRequestCreate`, `TaskRequestRead`, `ReservationRead`, `ConflictRead`, `ErrorResponse`.
- JSON datetime contract is UTC ISO-8601; UUIDs serialize as strings.

- [ ] **Step 1: Write serialization tests first**

Create tests covering:

```python
def test_task_request_contract_round_trip() -> None:
    payload = {
        "title": "Poplar assembly",
        "project": "Populus",
        "preferred_server_id": "00000000-0000-0000-0000-000000000010",
        "planned_start": "2026-09-18T00:00:00Z",
        "planned_duration_minutes": 2880,
        "requested_cpu_cores": 32,
        "requested_memory_gb": 128.0,
        "requested_gpu_count": 2,
        "preferred_gpu_ids": [0, 1],
        "note": "HiFi assembly",
    }
    model = TaskRequestCreate.model_validate(payload)
    assert model.preferred_gpu_ids == [0, 1]
    assert model.model_dump(mode="json")["planned_start"].endswith("Z")
```

Also test duplicate GPU IDs are rejected and negative CPU/GPU values are rejected by DTO validation.

- [ ] **Step 2: Run the contract test and verify failure**

Run:

```bash
uv run pytest packages/contracts/tests/test_serialization.py -q
```

Expected: FAIL because contract modules do not exist.

- [ ] **Step 3: Implement the Pydantic DTOs and shared string enums**

Use `ConfigDict(extra="forbid")` for request/write DTOs. Do not include server IP fields or full process command lines in any shared contract.

`TaskRequestCreate` must enforce:
- non-empty trimmed `title`;
- `planned_duration_minutes > 0`;
- `requested_cpu_cores >= 0`;
- `requested_gpu_count >= 0`;
- `requested_memory_gb is None or >= 0`;
- unique non-negative `preferred_gpu_ids`;
- if explicit GPU IDs are supplied, `requested_gpu_count == len(preferred_gpu_ids)`.

- [ ] **Step 4: Run contract tests**

Run:

```bash
uv run pytest packages/contracts/tests/test_serialization.py -q
uv run ruff check packages/contracts
uv run mypy packages/contracts/src
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/contracts services/core/src/labserver_core/domain/enums.py
git commit -m "feat: define core API contracts"
```

---

### Task 3: Implement framework-independent domain entities and request transitions

**Files:**
- Create: `services/core/src/labserver_core/domain/entities.py`
- Create: `services/core/src/labserver_core/domain/errors.py`
- Create: `services/core/src/labserver_core/domain/transitions.py`
- Create: `services/core/tests/unit/test_transitions.py`

**Interfaces:**
- Produces immutable/value-oriented entities: `User`, `ManagedServer`, `ServerCapacity`, `TaskRequest`, `Reservation`.
- Produces `transition_request(request, target, actor_role) -> TaskRequest`.
- Produces stable domain exceptions with `code`: `invalid_transition`, `forbidden`, `server_disabled`, `capacity_exceeded`, `not_found`, `validation_error`.

- [ ] **Step 1: Write failing state-machine tests**

Cover exactly:

```text
draft -> submitted
submitted -> approved
submitted -> rejected
draft -> cancelled
submitted -> cancelled
```

Reject at minimum:

```text
approved -> submitted
rejected -> approved
cancelled -> submitted
member -> approve
member -> reject
```

Also test submit fails when selected server is disabled.

- [ ] **Step 2: Verify tests fail**

Run:

```bash
uv run pytest services/core/tests/unit/test_transitions.py -q
```

Expected: FAIL because domain implementation does not exist.

- [ ] **Step 3: Implement pure transition functions**

Rules:
- transition functions receive domain entities and actor role explicitly;
- no SQLAlchemy imports;
- no FastAPI imports;
- no reading system time inside pure transition validation except through an injected `now` when needed;
- approved/rejected transitions require `admin`;
- submit validates enabled server and known capacity when capacity values are present;
- capacity override is represented by an explicit boolean parameter available only to admin application service, not silently inferred.

- [ ] **Step 4: Run unit tests and static checks**

```bash
uv run pytest services/core/tests/unit/test_transitions.py -q
uv run ruff check services/core/src/labserver_core/domain services/core/tests/unit
uv run mypy services/core/src/labserver_core/domain
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/core/src/labserver_core/domain services/core/tests/unit/test_transitions.py
git commit -m "feat: add request lifecycle domain model"
```

---

### Task 4: Create SQLite persistence, initial migration, repositories, and unit-of-work boundary

**Files:**
- Create: `services/core/src/labserver_core/config.py`
- Create: `services/core/src/labserver_core/persistence/database.py`
- Create: `services/core/src/labserver_core/persistence/models.py`
- Create: `services/core/src/labserver_core/persistence/repositories.py`
- Create: `services/core/src/labserver_core/persistence/unit_of_work.py`
- Create: `services/core/alembic.ini`
- Create: `services/core/migrations/env.py`
- Create: `services/core/migrations/versions/0001_initial_core.py`
- Create: `services/core/tests/persistence/test_migrations.py`
- Create: `services/core/tests/conftest.py`

**Interfaces:**
- Produces `create_engine_and_session_factory(database_url)`.
- Produces repository protocols/implementations for users, servers, requests, reservations.
- Produces `SqlAlchemyUnitOfWork` with one transaction around approval -> reservation creation.

**Initial schema:**

`users`
- `id` UUID primary key
- `username` unique
- `display_name`
- `role`
- `enabled`
- `created_at`, `updated_at`

`managed_servers`
- `id` UUID primary key
- `key` unique (logical key only)
- `display_name`
- `enabled`
- `cpu_cores` nullable integer
- `memory_gb` nullable real
- `gpu_count` nullable integer
- `created_at`, `updated_at`

`task_requests`
- fields from approved spec
- `preferred_gpu_ids` JSON nullable
- `status`
- `status_changed_by` UUID nullable FK users
- timestamps

`reservations`
- fields from approved spec
- `request_id` nullable unique FK task_requests
- `gpu_ids` JSON nullable
- timestamps

`audit_events`
- `id` UUID primary key
- `entity_type`
- `entity_id` UUID
- `action`
- `actor_id` UUID nullable FK users
- `occurred_at`
- `details` JSON nullable

Do **not** store IP addresses in `managed_servers`.

- [ ] **Step 1: Write migration tests first**

Test creates a temporary SQLite database, runs `alembic upgrade head`, and asserts the five tables above exist. Add an FK test that inserting a request with a nonexistent `requester_id` fails.

- [ ] **Step 2: Verify migration test fails**

```bash
uv run pytest services/core/tests/persistence/test_migrations.py -q
```

Expected: FAIL because migration/configuration does not exist.

- [ ] **Step 3: Implement database setup with SQLite foreign keys**

On every SQLite connection execute:

```sql
PRAGMA foreign_keys=ON;
```

Use SQLAlchemy 2.0 declarative mappings. Keep ORM models in `persistence/models.py`; do not return them from application services or API routes.

- [ ] **Step 4: Implement repository mapping and unit of work**

Repository methods return domain entities, not ORM rows. Required methods:

```python
UserRepository.get(user_id: UUID) -> User | None
ServerRepository.get(server_id: UUID) -> ManagedServer | None
ServerRepository.get_by_key(key: str) -> ManagedServer | None
RequestRepository.get(request_id: UUID) -> TaskRequest | None
RequestRepository.add(request: TaskRequest) -> None
ReservationRepository.get_by_request_id(request_id: UUID) -> Reservation | None
ReservationRepository.list_for_server(server_id: UUID, start: datetime, end: datetime) -> list[Reservation]
ReservationRepository.add(reservation: Reservation) -> None
```

- [ ] **Step 5: Run migration and repository tests**

```bash
uv run pytest services/core/tests/persistence -q
uv run ruff check services/core/src/labserver_core/persistence services/core/migrations
uv run mypy services/core/src/labserver_core/persistence
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add services/core/alembic.ini services/core/migrations services/core/src/labserver_core/config.py services/core/src/labserver_core/persistence services/core/tests
 git commit -m "feat: add SQLite persistence and initial migration"
```

---

### Task 5: Add actor authorization and logical user/server application services

**Files:**
- Create: `services/core/src/labserver_core/application/actors.py`
- Create: `services/core/src/labserver_core/application/ports.py`
- Create: `services/core/src/labserver_core/application/server_service.py`
- Create: `services/core/src/labserver_core/api/dependencies.py`
- Create: `services/core/tests/unit/test_authorization.py`

**Interfaces:**
- Produces `CurrentActor(user_id: UUID, role: UserRole)`.
- Produces `require_admin(actor)` and `require_self_or_admin(actor, owner_id)`.
- Produces server methods `create_server`, `update_server`, `list_servers`.
- Produces FastAPI dependency `get_current_actor()` that raises HTTP 401 by default until a later human-auth adapter replaces it.

- [ ] **Step 1: Write authorization tests**

Test:
- member cannot create/disable a managed server;
- admin can create/update a managed server;
- member can act on own request but not another member's request;
- disabled user actor is rejected by application boundary when loaded.

- [ ] **Step 2: Verify failure**

```bash
uv run pytest services/core/tests/unit/test_authorization.py -q
```

- [ ] **Step 3: Implement default-deny actor boundary**

Do not add `X-User`, `X-Admin`, hard-coded admin, or any other deployment-auth bypass. Tests use FastAPI `dependency_overrides` later.

- [ ] **Step 4: Run tests and commit**

```bash
uv run pytest services/core/tests/unit/test_authorization.py -q
git add services/core/src/labserver_core/application services/core/src/labserver_core/api/dependencies.py services/core/tests/unit/test_authorization.py
git commit -m "feat: add core authorization boundary"
```

---

### Task 6: Implement the advisory conflict engine with segment-based capacity evaluation

**Files:**
- Create: `services/core/src/labserver_core/domain/conflicts.py`
- Create: `services/core/tests/unit/test_conflicts.py`

**Interfaces:**
- Produces:

```python
evaluate_conflicts(
    candidate: Reservation,
    existing: Sequence[Reservation],
    capacity: ServerCapacity,
) -> list[Conflict]
```

`Conflict` includes:
- `resource`: cpu | memory | gpu | gpu_device
- `certainty`: confirmed | uncertain
- `start_at`, `end_at`
- `requested`
- `available`
- `conflicting_reservation_ids`
- human-readable `reason`

- [ ] **Step 1: Write failing tests for interval semantics**

Required cases:
1. `[10:00, 11:00)` and `[11:00, 12:00)` -> no conflict.
2. `[10:00, 11:00)` and `[10:59, 12:00)` -> overlap.
3. Candidate CPU 16 plus two overlapping 12-core reservations on a 32-core server -> conflict only in the segment where all three overlap.
4. Memory capacity unknown -> do not invent a confirmed memory conflict.
5. Explicit GPU IDs `[0,1]` vs `[1,2]` -> confirmed `gpu_device` conflict on GPU 1.
6. Explicit GPU IDs `[0,1]` vs `[2,3]` on four-GPU server -> no GPU-device conflict.
7. Candidate requests two GPUs without IDs while overlapping two-GPU count-only reservation on four-GPU server -> no aggregate conflict.
8. Same case with three-GPU existing reservation -> aggregate GPU conflict.
9. Candidate explicit GPU `[0]` overlaps count-only reservation -> mark device placement conflict `uncertain` only when aggregate capacity cannot prove safety.
10. Cancelled reservations do not consume capacity.

- [ ] **Step 2: Verify tests fail**

```bash
uv run pytest services/core/tests/unit/test_conflicts.py -q
```

- [ ] **Step 3: Implement a boundary sweep, not pairwise-only arithmetic**

Algorithm:
1. Filter same-server, non-cancelled reservations whose interval overlaps the candidate.
2. Collect candidate start/end plus all clipped overlap start/end boundaries.
3. Sort unique boundaries.
4. For each adjacent segment inside candidate, determine active existing reservations.
5. Sum CPU, memory (only when capacity known), and GPU counts including the candidate.
6. Evaluate explicit GPU-ID intersections separately.
7. Coalesce adjacent conflict segments with identical resource/certainty/conflicting set.

This prevents false negatives when several reservations overlap only part of the candidate window.

- [ ] **Step 4: Run tests and static checks**

```bash
uv run pytest services/core/tests/unit/test_conflicts.py -q
uv run ruff check services/core/src/labserver_core/domain/conflicts.py services/core/tests/unit/test_conflicts.py
uv run mypy services/core/src/labserver_core/domain/conflicts.py
```

- [ ] **Step 5: Commit**

```bash
git add services/core/src/labserver_core/domain/conflicts.py services/core/tests/unit/test_conflicts.py
git commit -m "feat: add advisory reservation conflict engine"
```

---

### Task 7: Implement request application service and transactional idempotent approval

**Files:**
- Create: `services/core/src/labserver_core/application/request_service.py`
- Create: `services/core/src/labserver_core/application/reservation_service.py`
- Create: `services/core/tests/unit/test_request_service.py`
- Create: `services/core/tests/persistence/test_approval_transaction.py`

**Interfaces:**
- Produces `create_request`, `update_draft`, `submit_request`, `cancel_request`, `reject_request`, `approve_request`.
- Produces `preview_request_conflicts(request_id, actor) -> list[Conflict]`.
- `approve_request` returns the created or already-existing reservation.

- [ ] **Step 1: Write application tests first**

Cover:
- member creates own draft;
- member cannot create a draft for another user;
- draft can be edited by owner;
- submitted request cannot be edited as draft;
- submitting validates server enabled and capacity;
- admin rejection stores status actor/audit event;
- admin approval creates one reservation;
- calling approval twice returns the same reservation ID;
- conflict warnings do not block approval;
- a failed reservation insert rolls back request status to `submitted`.

- [ ] **Step 2: Verify tests fail**

```bash
uv run pytest services/core/tests/unit/test_request_service.py services/core/tests/persistence/test_approval_transaction.py -q
```

- [ ] **Step 3: Implement application orchestration through repositories/UoW**

Approval sequence inside one UoW:

```text
load request
-> authorize admin
-> if already approved: load reservation by request_id and return it
-> validate transition submitted -> approved
-> build reservation with end_at = planned_start + duration
-> evaluate advisory conflicts
-> persist approved request + reservation + audit event
-> commit once
```

The DB unique constraint on `reservations.request_id` is a second idempotency guard.

- [ ] **Step 4: Run tests**

```bash
uv run pytest services/core/tests/unit/test_request_service.py services/core/tests/persistence/test_approval_transaction.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/core/src/labserver_core/application services/core/tests/unit/test_request_service.py services/core/tests/persistence/test_approval_transaction.py
git commit -m "feat: implement request approval workflow"
```

---

### Task 8: Expose thin versioned FastAPI routes and stable API errors

**Files:**
- Create: `services/core/src/labserver_core/api/errors.py`
- Create: `services/core/src/labserver_core/api/router.py`
- Create: `services/core/src/labserver_core/api/routes/health.py`
- Create: `services/core/src/labserver_core/api/routes/users.py`
- Create: `services/core/src/labserver_core/api/routes/servers.py`
- Create: `services/core/src/labserver_core/api/routes/requests.py`
- Create: `services/core/src/labserver_core/api/routes/reservations.py`
- Create: `services/core/src/labserver_core/app.py`
- Create: `services/core/tests/api/test_health.py`
- Create: `services/core/tests/api/test_servers.py`
- Create: `services/core/tests/api/test_requests.py`
- Create: `services/core/tests/api/test_approval.py`

**Interfaces:**
- `GET /healthz` — no auth; only verifies core process/database readiness, never calls lab hosts.
- `GET /api/v1/servers` — authenticated member/admin.
- `POST /api/v1/servers` — admin.
- `POST /api/v1/requests` — authenticated member/admin, creates own request unless admin acts explicitly.
- `PATCH /api/v1/requests/{id}` — owner while draft, or admin under service rules.
- `POST /api/v1/requests/{id}/submit`
- `POST /api/v1/requests/{id}/cancel`
- `POST /api/v1/requests/{id}/approve` — admin.
- `POST /api/v1/requests/{id}/reject` — admin.
- `GET /api/v1/reservations`
- `GET /api/v1/requests/{id}/conflicts` — preview advisory conflicts.

Stable error body:

```json
{
  "error": {
    "code": "invalid_transition",
    "message": "Request cannot transition from approved to submitted"
  }
}
```

- [ ] **Step 1: Write API tests with dependency overrides**

Use `app.dependency_overrides[get_current_actor] = lambda: CurrentActor(...)`.

Test unauthenticated calls to protected routes return `401`; member admin-only calls return `403`; domain errors map to deterministic codes and appropriate 4xx statuses.

- [ ] **Step 2: Verify API tests fail**

```bash
uv run pytest services/core/tests/api -q
```

- [ ] **Step 3: Implement thin routes**

Routes may:
- validate DTOs;
- resolve dependencies;
- call application services;
- map domain entities to contracts.

Routes may **not**:
- calculate conflicts;
- mutate statuses directly;
- create SQLAlchemy queries;
- inspect server IPs.

- [ ] **Step 4: Run API tests**

```bash
uv run pytest services/core/tests/api -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/core/src/labserver_core/api services/core/src/labserver_core/app.py services/core/tests/api
git commit -m "feat: expose core planning API"
```

---

### Task 9: Document the M1 API and enforce contract/architecture checks

**Files:**
- Create: `docs/api/core-v1.md`
- Create: `services/core/tests/test_architecture_boundaries.py`
- Modify: `README.md`

**Interfaces:**
- Documents route, role, request/response contract, and status/error semantics for all M1 endpoints.
- Adds a simple import-boundary test preventing route modules from importing ORM model modules directly.

- [ ] **Step 1: Write an architecture-boundary test**

The test parses imports under `services/core/src/labserver_core/api/routes/` and fails if a route imports:

```text
labserver_core.persistence.models
sqlalchemy
```

It also verifies `labserver_contracts` has no import from `labserver_core`.

- [ ] **Step 2: Run and verify the test catches a synthetic forbidden import**

Temporarily introduce the forbidden import in the test fixture/sample string, verify failure, then remove the synthetic violation before commit.

- [ ] **Step 3: Write `docs/api/core-v1.md`**

Document:
- auth requirement (`CurrentActor` boundary; human transport not yet implemented);
- role matrix;
- logical server identity rule;
- request state machine;
- approval idempotency;
- advisory conflict semantics;
- error envelope;
- explicit statement that M1 performs no remote execution or host polling.

- [ ] **Step 4: Update README status**

README should state Milestone 1 core is the current implementation target and link to the spec, plan, and API document.

- [ ] **Step 5: Commit**

```bash
git add docs/api services/core/tests/test_architecture_boundaries.py README.md
git commit -m "docs: define core v1 API and architecture checks"
```

---

### Task 10: Final Milestone 1 verification and current-state update

**Files:**
- Modify: `docs/CURRENT_STATE.md`

**Interfaces:**
- No new runtime interface. This task proves the milestone is internally coherent before PR review.

- [ ] **Step 1: Run full locked verification**

```bash
uv sync --all-packages --dev --locked
uv run ruff check .
uv run mypy services/core/src packages/contracts/src
uv run pytest -q
```

Expected: all commands PASS.

- [ ] **Step 2: Run migration from an empty database**

```bash
rm -f /tmp/labserver-m1-smoke.sqlite
LABSERVER_DATABASE_URL=sqlite:////tmp/labserver-m1-smoke.sqlite \
  uv run alembic -c services/core/alembic.ini upgrade head
```

Expected: exit `0`; initial schema is created with foreign keys enabled.

- [ ] **Step 3: Run an API smoke test with test dependency injection, never a real auth bypass**

Use `fastapi.testclient.TestClient` in a short test module/pytest test to confirm:
- `/healthz` returns 200;
- protected endpoint returns 401 without actor override;
- with test actor override, server/request CRUD path works against temporary SQLite.

- [ ] **Step 4: Secret/private-infrastructure scan**

Run repository grep for common secret/IP patterns and manually inspect the diff. Confirm no actual fwq host IP, token, password, SSH key, or lab username was committed.

- [ ] **Step 5: Update `docs/CURRENT_STATE.md`**

Only after verification passes, record:
- Milestone 1 implemented;
- exact verification commands and result;
- current implementation branch/PR;
- next gate is Milestone 2 design/plan for read-only Lab Agent + Running view.

- [ ] **Step 6: Commit**

```bash
git add docs/CURRENT_STATE.md
git commit -m "docs: record milestone 1 verification state"
```

---

## Milestone 1 Acceptance Criteria

Milestone 1 is complete only when all of the following are true:

1. A clean checkout can install strictly from `uv.lock` and run CI without lab-network access.
2. `labserver_contracts` is independently importable and contains no core/persistence dependency.
3. An empty SQLite database migrates to head successfully with foreign keys enforced.
4. Managed servers persist logical keys/capacities only; no private IP is persisted as identity.
5. Members/admins are represented in the domain and authorization rules are unit-tested.
6. Protected HTTP routes deny access by default; tests inject actors explicitly.
7. Request state transitions match the approved spec.
8. Approval is transactional and idempotent and creates at most one reservation per request.
9. Adjacent half-open reservations do not conflict; true overlapping aggregate CPU/memory/GPU over-capacity does.
10. Explicit GPU-ID collisions are reported; count-only placement uncertainty is labeled, not guessed.
11. Conflicts remain advisory and do not prevent approval unless a future approved policy changes that rule.
12. Routes contain no ORM queries or conflict calculations.
13. Full test/lint/type-check suite passes.
14. No real lab IP, credential, token, SSH material, or private username is present in the repository.

## Explicitly Deferred to Later Milestones

- Human login/session transport; M1 provides a default-deny actor boundary only.
- Linux username mapping and runtime process observations.
- Lab Agent, `psutil`, `nvitop`, and NVML.
- Beszel adapter and host metrics.
- SSE/current-state streaming.
- Browser UI, schedule timeline, and dashboard.
- Plan-vs-actual reconciliation.
- Usage statistics and availability forecasting.
- Production deployment, backup/restore, and real internal IP mapping.
