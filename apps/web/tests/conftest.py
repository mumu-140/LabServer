from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from labserver_contracts.common import UserRole
from labserver_contracts.monitoring import (
    DashboardRead,
    FreshnessStatus,
    HostMetricsRead,
    HostStatus,
    ServerDashboardCard,
)
from labserver_contracts.plans import (
    PlanConflictRead,
    PlanCreate,
    PlanRead,
    PlanUpdate,
)
from labserver_contracts.runtime import RuntimeOverviewRead
from labserver_contracts.servers import ServerRead
from labserver_contracts.users import UserCreate, UserRead, UserUpdate
from labserver_web.app import create_app
from labserver_web.auth import ViewerContext, get_current_viewer
from labserver_web.clients.core import CoreClient, CoreClientError
from labserver_web.config import WebSettings
from labserver_web.dependencies import get_core_client

NOW = datetime(2026, 9, 15, 9, 0, tzinfo=UTC)
START = datetime(2026, 9, 20, 8, 0, tzinfo=UTC)
SERVER_ID = UUID("00000000-0000-0000-0000-000000002001")
OTHER_SERVER_ID = UUID("00000000-0000-0000-0000-000000002004")
ALICE_ID = UUID("00000000-0000-0000-0000-000000002002")
BOB_ID = UUID("00000000-0000-0000-0000-000000002003")
BOB_SERVER_ID = UUID("00000000-0000-0000-0000-000000002005")


def plan_read(**overrides: Any) -> PlanRead:
    values: dict[str, Any] = {
        "id": str(uuid4()),
        "owner_id": str(ALICE_ID),
        "server_id": str(SERVER_ID),
        "title": "RNA-seq",
        "project": None,
        "start_at": "2026-09-20T08:00:00Z",
        "end_at": "2026-09-20T13:00:00Z",
        "cpu_cores": None,
        "memory_gb": None,
        "gpu_count": 1,
        "gpu_ids": [0],
        "note": None,
        "cancelled_at": None,
        "created_at": "2026-09-15T09:00:00Z",
        "updated_at": "2026-09-15T09:00:00Z",
        "display_state": "upcoming",
    }
    values.update(overrides)
    return PlanRead.model_validate(values)


def conflict_read(plan_id: str) -> PlanConflictRead:
    return PlanConflictRead.model_validate(
        {
            "resource": "gpu_device",
            "certainty": "confirmed",
            "start_at": "2026-09-20T08:00:00Z",
            "end_at": "2026-09-20T13:00:00Z",
            "requested": [0],
            "available": [],
            "conflicting_plan_ids": [plan_id],
            "reason": "GPU 0 already planned",
        }
    )


class FakeCoreClient(CoreClient):
    """Stand-in that never talks to a real Core service."""

    def __init__(
        self,
        *,
        plans: list[PlanRead] | None = None,
        servers: list[ServerRead] | None = None,
        users: list[UserRead] | None = None,
        conflicts: dict[UUID, list[PlanConflictRead]] | None = None,
        dashboard: DashboardRead | None = None,
        runtime_overview: RuntimeOverviewRead | None = None,
    ) -> None:
        self.plans = list(plans or [])
        self.servers = list(servers or [])
        self.users = list(users or [])
        self._conflicts = conflicts or {}
        self.dashboard = dashboard
        self.runtime_overview = runtime_overview
        self.calls: list[tuple[str, Any]] = []
        self.error: Exception | None = None
        self.fail_at = 0
        self._call_number = -1


    def _maybe_fail(self) -> None:
        self._call_number += 1
        if self.error is not None and self._call_number == self.fail_at:
            raise self.error

    def list_servers(self) -> list[ServerRead]:
        self._maybe_fail()
        self.calls.append(("list_servers", None))
        return list(self.servers)

    def list_users(self, *, cookies: dict[str, str] | None = None) -> list[UserRead]:
        self._maybe_fail()
        self.calls.append(("list_users", cookies))
        return list(self.users)

    def create_user(
        self, data: UserCreate, *, cookies: dict[str, str] | None = None
    ) -> UserRead:
        self._maybe_fail()
        self.calls.append(("create_user", {"data": data, "cookies": cookies}))
        user = UserRead(
            id=uuid4(),
            username=data.username,
            display_name=data.display_name,
            role=data.role,
            enabled=data.enabled,
            created_at=NOW,
            updated_at=NOW,
        )
        self.users.append(user)
        return user

    def set_user_password(
        self, user_id: UUID, password: str, *, cookies: dict[str, str] | None = None
    ) -> None:
        self._maybe_fail()
        self.calls.append(
            (
                "set_user_password",
                {"user_id": user_id, "password": password, "cookies": cookies},
            )
        )

    def update_user(
        self, user_id: UUID, data: UserUpdate, *, cookies: dict[str, str] | None = None
    ) -> UserRead:
        self._maybe_fail()
        self.calls.append(
            ("update_user", {"user_id": user_id, "data": data, "cookies": cookies})
        )
        for i, u in enumerate(self.users):
            if u.id == user_id:
                updated = UserRead(
                    id=u.id,
                    username=u.username,
                    display_name=data.display_name if data.display_name is not None else u.display_name,
                    role=data.role if data.role is not None else u.role,
                    enabled=data.enabled if data.enabled is not None else u.enabled,
                    created_at=u.created_at,
                    updated_at=NOW,
                )
                self.users[i] = updated
                return updated
        raise CoreClientError(404, "not_found", "User not found")

    def list_plans(
        self,
        *,
        server_id: UUID | None = None,
        owner_id: UUID | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        include_cancelled: bool = False,
    ) -> list[PlanRead]:
        self._maybe_fail()
        self.calls.append(
            (
                "list_plans",
                {
                    "server_id": server_id,
                    "owner_id": owner_id,
                    "start": start,
                    "end": end,
                    "include_cancelled": include_cancelled,
                },
            )
        )
        return list(self.plans)

    def get_plan(self, plan_id: UUID) -> PlanRead:
        self._maybe_fail()
        self.calls.append(("get_plan", plan_id))
        for plan in self.plans:
            if plan.id == str(plan_id):
                return plan
        return plan_read(id=str(plan_id))

    def list_conflicts(self, plan_id: UUID) -> list[PlanConflictRead]:
        self._maybe_fail()
        self.calls.append(("list_conflicts", plan_id))
        return list(self._conflicts.get(plan_id, []))

    def update_plan(self, plan_id: UUID, data: PlanUpdate) -> PlanRead:
        self._maybe_fail()
        self.calls.append(("update_plan", {"plan_id": plan_id, "data": data}))
        return plan_read(id=str(plan_id))

    def create_plan(self, data: PlanCreate) -> PlanRead:
        self._maybe_fail()
        self.calls.append(("create_plan", data))
        created = plan_read(
            id=str(uuid4()),
            server_id=str(data.server_id),
            title=data.title,
            start_at=data.start_at.isoformat(),
            end_at=data.end_at.isoformat(),
            gpu_count=data.gpu_count,
            gpu_ids=list(data.gpu_ids) if data.gpu_ids is not None else None,
            cpu_cores=data.cpu_cores,
            memory_gb=data.memory_gb,
            project=data.project,
            note=data.note,
        )
        self.plans.append(created)
        return created

    def cancel_plan(self, plan_id: UUID) -> PlanRead:
        self._maybe_fail()
        self.calls.append(("cancel_plan", plan_id))
        return plan_read(
            id=str(plan_id),
            cancelled_at="2026-09-15T10:00:00Z",
            display_state="cancelled",
        )

    def get_dashboard(self, *, cookies: dict[str, str] | None = None) -> DashboardRead:
        self._maybe_fail()
        self.calls.append(("get_dashboard", cookies))
        if self.dashboard is not None:
            return self.dashboard
        now = datetime.now(UTC)
        cards = [
            ServerDashboardCard(
                server=s,
                metrics=HostMetricsRead(
                    server_key=s.key,
                    status=HostStatus.UP,
                    freshness=FreshnessStatus.FRESH,
                    cpu_percent=10.0,
                    memory_percent=30.0,
                    disk_percent=40.0,
                ),
                active_plans_count=0,
                near_term_plans=[],
            )
            for s in self.servers
        ]
        return DashboardRead(cards=cards, observed_at=now)

    def get_runtime_overview(
        self, *, cookies: dict[str, str] | None = None
    ) -> RuntimeOverviewRead:
        self._maybe_fail()
        self.calls.append(("get_runtime_overview", {"cookies": cookies}))
        if self.runtime_overview is not None:
            return self.runtime_overview
        now = datetime.now(UTC)
        return RuntimeOverviewRead(servers=[], observed_at=now)




def server_read(
    server_id: UUID = SERVER_ID, key: str = "fwq10", display_name: str = "fwq10"
) -> ServerRead:
    return ServerRead.model_validate(
        {
            "id": str(server_id),
            "key": key,
            "display_name": display_name,
            "enabled": True,
            "cpu_cores": 64,
            "memory_gb": 256.0,
            "gpu_count": 4,
            "created_at": "2026-09-15T00:00:00Z",
            "updated_at": "2026-09-15T00:00:00Z",
        }
    )


def user_read(user_id: UUID = ALICE_ID, username: str = "alice") -> UserRead:
    return UserRead.model_validate(
        {
            "id": str(user_id),
            "username": username,
            "display_name": username.title(),
            "role": UserRole.MEMBER.value,
            "enabled": True,
            "created_at": "2026-09-15T00:00:00Z",
            "updated_at": "2026-09-15T00:00:00Z",
        }
    )


def _make_app(fake_core: FakeCoreClient) -> Any:
    app = create_app(
        WebSettings(core_base_url="http://core.test", timezone_name="Asia/Shanghai")
    )
    app.dependency_overrides[get_core_client] = lambda: fake_core
    return app


def _client_for(
    app: Any, viewer: ViewerContext | None = None
) -> TestClient:  # pragma: no cover - fixture helper
    if viewer is not None:
        app.dependency_overrides[get_current_viewer] = lambda: viewer
    return TestClient(app)


@pytest.fixture
def app(fake_core: FakeCoreClient) -> Any:
    return _make_app(fake_core)


@pytest.fixture
def client(app: Any) -> TestClient:
    app.dependency_overrides[get_current_viewer] = lambda: ViewerContext(
        user_id=ALICE_ID, role=UserRole.MEMBER
    )
    with _client_for(app) as test_client:
        yield test_client


@pytest.fixture
def bob_client(app: Any) -> TestClient:
    app.dependency_overrides[get_current_viewer] = lambda: ViewerContext(
        user_id=BOB_ID, role=UserRole.MEMBER
    )
    with _client_for(app) as test_client:
        yield test_client


@pytest.fixture
def admin_client(app: Any) -> TestClient:
    app.dependency_overrides[get_current_viewer] = lambda: ViewerContext(
        user_id=BOB_ID, role=UserRole.ADMIN
    )
    with _client_for(app) as test_client:
        yield test_client


@pytest.fixture
def anonymous_client(fake_core: FakeCoreClient) -> TestClient:
    with _client_for(_make_app(fake_core)) as test_client:
        yield test_client


@pytest.fixture
def fake_core() -> FakeCoreClient:
    return FakeCoreClient(
        servers=[
            server_read(),
            server_read(BOB_SERVER_ID, "fwq51", "fwq51"),
        ],
        users=[user_read(ALICE_ID, "alice"), user_read(BOB_ID, "bob")],
    )
