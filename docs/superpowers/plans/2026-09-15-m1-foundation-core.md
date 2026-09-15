# Milestone 1 Foundation + Core Planning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a testable central LabServer core that stores users, logical servers, task requests, reservations, performs request lifecycle/approval and advisory resource-conflict evaluation, and exposes versioned HTTP APIs without requiring any lab host, GPU, Beszel instance, or private-network access.

**Architecture:** Use a small Python monorepo workspace with an independent contracts package and a FastAPI core service. Business rules live in framework-independent domain/application modules; SQLAlchemy/Alembic are persistence adapters; HTTP routes are thin adapters. Human authentication transport is intentionally deferred: Milestone 1 exposes a `CurrentActor` authorization boundary that is **default-deny** unless a trusted adapter/test override supplies an actor. No temporary header-based admin bypass is allowed.

**Tech Stack:** Python 3.13; uv workspace/lockfile; FastAPI 0.141.1; Pydantic 2.13.5; SQLAlchemy 2.0.52; Alembic 1.20.0; Uvicorn 0.52.4; HTTPX 0.28.1; SQLite; pytest 9.1.1; Ruff 0.16.7; mypy 2.3.1; GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-15-labserver-design.md`

## Global Constraints

- V1 is observation + planning + reconciliation + reporting, **not** a scheduler.
- No real server IPs, credentials, SSH material, user secrets, or private command lines may enter Git.
- Server identity is a stable logical key such as `fwq10`; IP addresses are runtime configuration and are not database identity.
- Core tests must run without network access, Beszel, Linux process access, or a GPU.
- SQLite is the Milestone 1 database; foreign keys are enabled and migrations exist from the first schema.
- Timestamps are timezone-aware and normalized to UTC.
- Task request and reservation are separate persisted concepts.
- Approval creates a reservation in one transaction and is idempotent.
- Scheduling intervals are half-open: `[start, end)`.
- Conflicts are advisory in V1; conflict detection never dispatches, blocks, kills, or moves workloads.
- Business rules belong in `services/core/src/labserver_core/domain` or `application`, never in routes or ORM models.
- Shared API schemas/enums belong in `packages/contracts`; contracts contain no database access or service logic.
- Shared enums have one source of truth in `labserver_contracts.common`; core imports them and does not redefine them.
- HTTP authorization defaults to deny until a real human-auth adapter is implemented.
- Python runtime baseline is 3.13; prerelease dependencies are forbidden in this milestone.

---

## File Structure Locked by This Plan

```text
LabServer/
├── pyproject.toml
├── uv.lock
├── .python-version
├── .github/workflows/ci.yml
├── packages/contracts/
│   ├── pyproject.toml
│   ├── src/labserver_contracts/
│   │   ├── __init__.py
│   │   ├── common.py
│   │   ├── users.py
│   │   ├── servers.py
│   │   ├── requests.py
│   │   └── reservations.py
│   └── tests/
│       ├── test_imports.py
│       └── test_serialization.py
├── services/core/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── migrations/
│   │   ├── env.py
│   │   └── versions/0001_initial_core.py
│   ├── src/labserver_core/
│   │   ├── __init__.py
│   │   ├── app.py
│   │   ├── config.py
│   │   ├── api/
│   │   │   ├── dependencies.py
│   │   │   ├── errors.py
│   │   │   ├── router.py
│   │   │   └── routes/{health,users,servers,requests,reservations}.py
│   │   ├── application/
│   │   │   ├── actors.py
│   │   │   ├── ports.py
│   │   │   ├── user_service.py
│   │   │   ├── server_service.py
│   │   │   ├── request_service.py
│   │   │   └── reservation_service.py
│   │   ├── domain/
│   │   │   ├── entities.py
│   │   │   ├── errors.py
│   │   │   ├── transitions.py
│   │   │   └── conflicts.py
│   │   └── persistence/
│   │       ├── database.py
│   │       ├── models.py
│   │       ├── repositories.py
│   │       └── unit_of_work.py
│   └── tests/
│       ├── conftest.py
│       ├── test_architecture_boundaries.py
│       ├── unit/{test_authorization,test_request_service,test_transitions,test_conflicts}.py
│       ├── persistence/{test_approval_transaction,test_migrations}.py
│       └── api/{test_health,test_users,test_servers,test_requests,test_approval}.py
└── docs/api/core-v1.md
```

No `apps/web`, `services/agent`, Beszel adapter, SSE endpoint, or deployment-to-real-host file is added in Milestone 1.

---

### Task 1: Establish the Python workspace and a green CI baseline

**Files:**
- Create: `pyproject.toml`
- Create: `.python-version`
- Create: `packages/contracts/pyproject.toml`
- Create: `packages/contracts/src/labserver_contracts/__init__.py`
- Create: `packages/contracts/tests/test_imports.py`
- Create: `services/core/pyproject.toml`
- Create: `services/core/src/labserver_core/__init__.py`
- Create: `.github/workflows/ci.yml`
- Generate/commit: `uv.lock`

**Interfaces:**
- Produces importable packages `labserver_contracts` and `labserver_core`.
- Produces workspace commands `uv run pytest`, `uv run ruff check .`, and `uv run mypy ...`.

- [ ] **Step 1: Add exact workspace configuration**

Root `pyproject.toml`:

```toml
[project]
name = "labserver-workspace"
version = "0.0.0"
requires-python = ">=3.13,<3.14"

[tool.uv]
package = false

[tool.uv.workspace]
members = ["packages/contracts", "services/core"]

[dependency-groups]
dev = [
  "httpx==0.28.1",
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
  "uvicorn==0.52.4",
]

[tool.uv.sources]
labserver-contracts = { workspace = true }

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

`.python-version` contains exactly `3.13`.

- [ ] **Step 2: Add a real smoke test so the first CI commit is green**

`packages/contracts/tests/test_imports.py`:

```python
def test_workspace_packages_import() -> None:
    import labserver_contracts
    import labserver_core

    assert labserver_contracts.__name__ == "labserver_contracts"
    assert labserver_core.__name__ == "labserver_core"
```

- [ ] **Step 3: Generate lockfile and run the baseline**

```bash
uv lock
uv sync --all-packages --dev --locked
uv run ruff check .
uv run mypy services/core/src packages/contracts/src
uv run pytest -q
```

Expected: all commands exit `0`; one smoke test passes.

- [ ] **Step 4: Add CI**

`.github/workflows/ci.yml` runs on `ubuntu-24.04`, Python 3.13 and executes the four locked commands above. It must not define lab IPs, SSH secrets, VPN setup, or service containers.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .python-version uv.lock .github packages/contracts services/core
git commit -m "chore: establish Python workspace and CI"
```

---

### Task 2: Define shared contracts and the one canonical enum set

**Files:**
- Create: `packages/contracts/src/labserver_contracts/common.py`
- Create: `packages/contracts/src/labserver_contracts/users.py`
- Create: `packages/contracts/src/labserver_contracts/servers.py`
- Create: `packages/contracts/src/labserver_contracts/requests.py`
- Create: `packages/contracts/src/labserver_contracts/reservations.py`
- Modify: `packages/contracts/src/labserver_contracts/__init__.py`
- Create: `packages/contracts/tests/test_serialization.py`

**Interfaces:**
- `labserver_contracts.common`: `UserRole`, `TaskRequestStatus`, `ReservationStatus`, `ReservationSource`, `ConflictCertainty`, `ConflictResource`, `ErrorResponse`.
- User DTOs: `UserCreate`, `UserRead`.
- Server DTOs: `ServerCreate`, `ServerUpdate`, `ServerRead`.
- Request DTOs: `TaskRequestCreate`, `TaskRequestUpdate`, `TaskRequestRead`.
- Reservation DTOs: `ReservationRead`, `ConflictRead`.
- UUIDs serialize as strings; datetimes are timezone-aware and normalized to UTC.

- [ ] **Step 1: Write failing serialization/validation tests**

```python
from datetime import timedelta


def test_task_request_contract_normalizes_utc() -> None:
    model = TaskRequestCreate.model_validate(
        {
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
    )
    assert model.preferred_gpu_ids == [0, 1]
    assert model.planned_start.utcoffset() == timedelta(0)
```

Also test rejection of duplicate/negative GPU IDs, negative resources, zero duration, naive datetimes, and explicit GPU IDs whose count differs from `requested_gpu_count`.

- [ ] **Step 2: Verify failure**

```bash
uv run pytest packages/contracts/tests/test_serialization.py -q
```

- [ ] **Step 3: Implement DTOs**

Use `ConfigDict(extra="forbid")` on write DTOs. No contract may contain a real/private endpoint field or full process command line.

- [ ] **Step 4: Verify**

```bash
uv run pytest packages/contracts/tests -q
uv run ruff check packages/contracts
uv run mypy packages/contracts/src
```

- [ ] **Step 5: Commit**

```bash
git add packages/contracts
git commit -m "feat: define core API contracts"
```

---

### Task 3: Implement pure domain entities and request lifecycle

**Files:**
- Create: `services/core/src/labserver_core/domain/entities.py`
- Create: `services/core/src/labserver_core/domain/errors.py`
- Create: `services/core/src/labserver_core/domain/transitions.py`
- Create: `services/core/tests/unit/test_transitions.py`

**Interfaces:**
- Entities: `User`, `ManagedServer`, `ServerCapacity`, `TaskRequest`, `Reservation`.
- Shared enums imported from `labserver_contracts.common`.
- Function: `transition_request(request, target, actor_role, *, server, allow_capacity_override=False) -> TaskRequest`.
- Domain errors expose stable `code`: `invalid_transition`, `forbidden`, `server_disabled`, `capacity_exceeded`, `not_found`, `validation_error`.

- [ ] **Step 1: Write failing transition tests**

Allowed:

```text
draft -> submitted
submitted -> approved
submitted -> rejected
draft -> cancelled
submitted -> cancelled
```

Forbidden at minimum:

```text
approved -> submitted
rejected -> approved
cancelled -> submitted
member -> approve
member -> reject
```

Also test submit fails against a disabled server and fails when known capacity is exceeded unless an explicit admin override is supplied.

- [ ] **Step 2: Verify failure**

```bash
uv run pytest services/core/tests/unit/test_transitions.py -q
```

- [ ] **Step 3: Implement pure functions**

No FastAPI or SQLAlchemy imports. Time-dependent behavior receives `now` as an argument when needed; domain code does not read wall clock implicitly.

- [ ] **Step 4: Verify and commit**

```bash
uv run pytest services/core/tests/unit/test_transitions.py -q
uv run ruff check services/core/src/labserver_core/domain services/core/tests/unit
uv run mypy services/core/src/labserver_core/domain
git add services/core/src/labserver_core/domain services/core/tests/unit/test_transitions.py
git commit -m "feat: add request lifecycle domain model"
```

---

### Task 4: Add SQLite persistence, migrations, repositories, and unit of work

**Files:**
- Create: `services/core/src/labserver_core/config.py`
- Create: `services/core/src/labserver_core/persistence/{database,models,repositories,unit_of_work}.py`
- Create: `services/core/alembic.ini`
- Create: `services/core/migrations/env.py`
- Create: `services/core/migrations/versions/0001_initial_core.py`
- Create: `services/core/tests/persistence/test_migrations.py`
- Create: `services/core/tests/conftest.py`

**Interfaces:**
- `create_engine_and_session_factory(database_url)`.
- `SqlAlchemyUnitOfWork` owns one SQLAlchemy Session/transaction.
- Repositories return domain entities, never ORM rows.

**Schema:**

`users`: UUID PK, unique username, display_name, role, enabled, timestamps.

`managed_servers`: UUID PK, unique logical `key`, display_name, enabled, nullable `cpu_cores`, `memory_gb`, `gpu_count`, timestamps. **No IP column.**

`task_requests`: approved-spec fields, JSON `preferred_gpu_ids`, status, nullable FK `status_changed_by`, timestamps.

`reservations`: approved-spec fields, nullable unique FK `request_id`, JSON `gpu_ids`, timestamps.

`audit_events`: UUID PK, entity_type, entity_id, action, nullable actor FK, occurred_at, nullable JSON details.

- [ ] **Step 1: Write failing migration tests**

Create a temporary SQLite DB, run `alembic upgrade head`, assert all five tables, assert `managed_servers` has no `ip`/`endpoint` column, and assert FK failure for a nonexistent request owner.

- [ ] **Step 2: Verify failure**

```bash
uv run pytest services/core/tests/persistence/test_migrations.py -q
```

- [ ] **Step 3: Implement DB setup**

Enable on every SQLite connection:

```sql
PRAGMA foreign_keys=ON;
```

Use SQLAlchemy 2.0 declarative models. `alembic.ini` must use a script location relative to its own directory so the root-level command works.

- [ ] **Step 4: Implement repository API**

```python
UserRepository.get(user_id: UUID) -> User | None
UserRepository.add(user: User) -> None
UserRepository.list_all() -> list[User]

ServerRepository.get(server_id: UUID) -> ManagedServer | None
ServerRepository.get_by_key(key: str) -> ManagedServer | None
ServerRepository.add(server: ManagedServer) -> None
ServerRepository.list_all() -> list[ManagedServer]

RequestRepository.get(request_id: UUID) -> TaskRequest | None
RequestRepository.add(request: TaskRequest) -> None
RequestRepository.list_for_user(user_id: UUID) -> list[TaskRequest]
RequestRepository.list_all() -> list[TaskRequest]

ReservationRepository.get_by_request_id(request_id: UUID) -> Reservation | None
ReservationRepository.list_for_server(server_id: UUID, start: datetime, end: datetime) -> list[Reservation]
ReservationRepository.list_window(start: datetime, end: datetime) -> list[Reservation]
ReservationRepository.add(reservation: Reservation) -> None
```

- [ ] **Step 5: Verify and commit**

```bash
uv run pytest services/core/tests/persistence -q
uv run ruff check services/core/src/labserver_core/persistence services/core/migrations
uv run mypy services/core/src/labserver_core/persistence
git add services/core/alembic.ini services/core/migrations services/core/src/labserver_core/config.py services/core/src/labserver_core/persistence services/core/tests
git commit -m "feat: add SQLite persistence and initial migration"
```

---

### Task 5: Add authorization plus user/server application services

**Files:**
- Create: `services/core/src/labserver_core/application/actors.py`
- Create: `services/core/src/labserver_core/application/ports.py`
- Create: `services/core/src/labserver_core/application/user_service.py`
- Create: `services/core/src/labserver_core/application/server_service.py`
- Create: `services/core/src/labserver_core/api/dependencies.py`
- Create: `services/core/tests/unit/test_authorization.py`

**Interfaces:**
- `CurrentActor(user_id: UUID, role: UserRole)`.
- `require_admin(actor)` and `require_self_or_admin(actor, owner_id)`.
- `UserService.create_user/list_users` — admin only.
- `ServerService.create_server/update_server/list_servers` — writes admin only; reads member/admin.
- `get_current_actor()` raises HTTP 401 by default.

- [ ] **Step 1: Write failing authorization tests**

Test admin/member rules, disabled actor rejection, member ownership boundaries, duplicate server logical-key error, and that server creation has no endpoint/IP input.

- [ ] **Step 2: Verify failure**

```bash
uv run pytest services/core/tests/unit/test_authorization.py -q
```

- [ ] **Step 3: Implement default-deny boundary**

No `X-User`, `X-Admin`, hard-coded admin, dev superuser, or similar bypass. Later API tests use FastAPI `dependency_overrides` only.

- [ ] **Step 4: Verify and commit**

```bash
uv run pytest services/core/tests/unit/test_authorization.py -q
git add services/core/src/labserver_core/application services/core/src/labserver_core/api/dependencies.py services/core/tests/unit/test_authorization.py
git commit -m "feat: add user server and authorization services"
```

---

### Task 6: Implement the advisory conflict engine with a boundary sweep

**Files:**
- Create: `services/core/src/labserver_core/domain/conflicts.py`
- Create: `services/core/tests/unit/test_conflicts.py`

**Interfaces:**

```python
evaluate_conflicts(
    candidate: Reservation,
    existing: Sequence[Reservation],
    capacity: ServerCapacity,
) -> list[Conflict]
```

`Conflict` contains `resource`, `certainty`, segment start/end, requested, available, conflicting reservation IDs, and reason.

- [ ] **Step 1: Write failing cases**

Required:
1. Adjacent `[10:00,11:00)` / `[11:00,12:00)` => no conflict.
2. One-minute overlap => overlap.
3. Candidate CPU 16 + two 12-core reservations on a 32-core server => conflict only where all three overlap.
4. Unknown memory capacity => no invented confirmed memory conflict.
5. Explicit GPU `[0,1]` vs `[1,2]` => confirmed device conflict on GPU 1.
6. Explicit GPU `[0,1]` vs `[2,3]` on four GPUs => no device conflict.
7. Two count-only + two count-only on four GPUs => no aggregate conflict.
8. Two count-only + three count-only on four GPUs => confirmed aggregate conflict.
9. Explicit GPU candidate overlapping a count-only reservation => `uncertain` device-placement warning because exact assignment is unknowable; if aggregate GPU capacity is exceeded, also return a confirmed aggregate GPU conflict.
10. Cancelled reservations consume no capacity.

- [ ] **Step 2: Verify failure**

```bash
uv run pytest services/core/tests/unit/test_conflicts.py -q
```

- [ ] **Step 3: Implement segment sweep**

Filter same-server/non-cancelled overlaps; collect clipped time boundaries; evaluate each adjacent segment; sum candidate + active reservations for CPU/memory/GPU; evaluate explicit device intersections separately; coalesce adjacent identical conflict segments.

- [ ] **Step 4: Verify and commit**

```bash
uv run pytest services/core/tests/unit/test_conflicts.py -q
uv run ruff check services/core/src/labserver_core/domain/conflicts.py services/core/tests/unit/test_conflicts.py
uv run mypy services/core/src/labserver_core/domain/conflicts.py
git add services/core/src/labserver_core/domain/conflicts.py services/core/tests/unit/test_conflicts.py
git commit -m "feat: add advisory reservation conflict engine"
```

---

### Task 7: Implement request service and transactional idempotent approval

**Files:**
- Create: `services/core/src/labserver_core/application/request_service.py`
- Create: `services/core/src/labserver_core/application/reservation_service.py`
- Create: `services/core/tests/unit/test_request_service.py`
- Create: `services/core/tests/persistence/test_approval_transaction.py`

**Interfaces:**
- `create_request`, `list_requests`, `get_request`, `update_draft`, `submit_request`, `cancel_request`, `reject_request`, `approve_request`.
- `list_reservations` and `preview_request_conflicts`.
- `approve_request` returns the created or already-existing reservation.

- [ ] **Step 1: Write failing service tests**

Cover owner creation/editing, cross-user denial, submitted-edit denial, enabled/capacity validation, audit actor on rejection, one reservation on approval, same reservation on repeated approval, advisory conflicts not blocking approval, and rollback to `submitted` if reservation persistence fails.

- [ ] **Step 2: Verify failure**

```bash
uv run pytest services/core/tests/unit/test_request_service.py services/core/tests/persistence/test_approval_transaction.py -q
```

- [ ] **Step 3: Implement approval in one UoW**

```text
load request
-> authorize admin
-> if approved: return reservation by request_id
-> validate submitted -> approved
-> build reservation (end = start + duration)
-> evaluate advisory conflicts
-> persist request + reservation + audit event
-> commit once
```

`reservations.request_id` unique constraint is the second idempotency guard.

- [ ] **Step 4: Verify and commit**

```bash
uv run pytest services/core/tests/unit/test_request_service.py services/core/tests/persistence/test_approval_transaction.py -q
git add services/core/src/labserver_core/application services/core/tests/unit/test_request_service.py services/core/tests/persistence/test_approval_transaction.py
git commit -m "feat: implement request approval workflow"
```

---

### Task 8: Expose thin versioned FastAPI routes with stable error codes

**Files:**
- Create: `services/core/src/labserver_core/api/errors.py`
- Create: `services/core/src/labserver_core/api/router.py`
- Create: `services/core/src/labserver_core/api/routes/{health,users,servers,requests,reservations}.py`
- Create: `services/core/src/labserver_core/app.py`
- Create: `services/core/tests/api/{test_health,test_users,test_servers,test_requests,test_approval}.py`

**Interfaces:**
- `GET /healthz` — no auth; process + DB readiness only, never lab hosts.
- `GET/POST /api/v1/users` — admin.
- `GET /api/v1/servers` — member/admin; `POST /api/v1/servers` — admin.
- `GET /api/v1/requests` — member sees own; admin sees all.
- `GET /api/v1/requests/{id}` — owner/admin.
- `POST /api/v1/requests` — creates own request; admin may explicitly choose owner through application service only if contract provides that field later via approved change.
- `PATCH /api/v1/requests/{id}` — owner while draft/admin per service rules.
- `POST /api/v1/requests/{id}/{submit|cancel}` — owner/admin per service rules.
- `POST /api/v1/requests/{id}/{approve|reject}` — admin.
- `GET /api/v1/requests/{id}/conflicts` — owner/admin.
- `GET /api/v1/reservations?start=&end=&server_id=` — member/admin.

Stable error envelope:

```json
{
  "error": {
    "code": "invalid_transition",
    "message": "Request cannot transition from approved to submitted"
  }
}
```

- [ ] **Step 1: Write failing API tests using dependency overrides**

Protected route without override => `401`; member on admin route => `403`; invalid transition/capacity/not-found errors map to deterministic codes and 4xx statuses.

- [ ] **Step 2: Verify failure**

```bash
uv run pytest services/core/tests/api -q
```

- [ ] **Step 3: Implement thin routes**

Routes only validate DTOs, resolve dependencies, call application services, and map entities to contracts. They may not query SQLAlchemy, calculate conflicts, directly mutate lifecycle status, or inspect IPs.

- [ ] **Step 4: Verify and commit**

```bash
uv run pytest services/core/tests/api -q
git add services/core/src/labserver_core/api services/core/src/labserver_core/app.py services/core/tests/api
git commit -m "feat: expose core planning API"
```

---

### Task 9: Document Core v1 and enforce architecture boundaries

**Files:**
- Create: `docs/api/core-v1.md`
- Create: `services/core/tests/test_architecture_boundaries.py`
- Modify: `README.md`

**Interfaces:**
- Documents route/role/request/response/error semantics.
- Adds source-level guard against API routes importing ORM/SQLAlchemy internals.

- [ ] **Step 1: Write the architecture guard test**

Parse imports under `api/routes/` and reject `labserver_core.persistence.models` or direct `sqlalchemy` imports. Also scan `packages/contracts/src` and reject any `labserver_core` import. Prove the checker using synthetic source strings inside the test, not by modifying production code.

- [ ] **Step 2: Verify**

```bash
uv run pytest services/core/tests/test_architecture_boundaries.py -q
```

- [ ] **Step 3: Write `docs/api/core-v1.md`**

Document default-deny actor boundary, role matrix, logical server identity, request state machine, idempotent approval, advisory conflict semantics, error envelope, and explicit statement that M1 performs no host polling/remote execution.

- [ ] **Step 4: Update README and commit**

```bash
git add docs/api services/core/tests/test_architecture_boundaries.py README.md
git commit -m "docs: define core v1 API and architecture checks"
```

---

### Task 10: Final M1 verification and state update

**Files:**
- Modify: `docs/CURRENT_STATE.md`

- [ ] **Step 1: Run locked verification**

```bash
uv sync --all-packages --dev --locked
uv run ruff check .
uv run mypy services/core/src packages/contracts/src
uv run pytest -q
```

All commands must PASS.

- [ ] **Step 2: Migrate an empty database**

```bash
rm -f /tmp/labserver-m1-smoke.sqlite
LABSERVER_DATABASE_URL=sqlite:////tmp/labserver-m1-smoke.sqlite \
  uv run alembic -c services/core/alembic.ini upgrade head
```

Expected: exit `0` and initial schema created.

- [ ] **Step 3: API smoke test**

Use `fastapi.testclient.TestClient` in pytest: `/healthz` => 200; protected endpoint => 401 without actor; actor override enables user/server/request flow against temporary SQLite. Never create a production auth bypass for this smoke test.

- [ ] **Step 4: Secret/private-infrastructure scan**

Search diff/repository for credential/private-IP/key patterns and manually inspect it. Confirm no real fwq IP, token, password, SSH material, or lab username was committed.

- [ ] **Step 5: Update state only after all evidence passes**

`docs/CURRENT_STATE.md` records M1 as implemented, the exact verification commands, implementation PR, and next gate: M2 read-only Lab Agent + Running view plan.

- [ ] **Step 6: Commit**

```bash
git add docs/CURRENT_STATE.md
git commit -m "docs: record milestone 1 verification state"
```

---

## Milestone 1 Acceptance Criteria

1. Clean checkout installs from `uv.lock` and CI runs without lab-network access.
2. Every task ends with passing tests/checks; no intermediate task intentionally leaves CI red.
3. `labserver_contracts` has no core/persistence dependency.
4. Shared lifecycle/role enums exist only in `labserver_contracts.common`.
5. Empty SQLite migrates to head with foreign keys enforced.
6. Managed servers persist logical keys/capacities only; no private IP is database identity.
7. Member/admin authorization is unit-tested and HTTP protected routes deny by default.
8. Request transitions match the approved spec.
9. Approval is transactional/idempotent and creates at most one reservation per request.
10. Half-open interval, aggregate CPU/memory/GPU, explicit GPU-ID, and uncertain count-only placement cases are tested.
11. Conflicts remain advisory.
12. API routes contain no ORM queries or conflict calculations.
13. Full test/lint/type-check suite passes.
14. Repository contains no real lab IP, credential, token, SSH material, or private username.

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
