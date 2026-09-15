from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from labserver_contracts.common import UserRole
from labserver_contracts.plans import PlanConflictRead, PlanCreate, PlanRead
from labserver_contracts.servers import ServerRead
from labserver_contracts.users import UserRead
from labserver_web.app import create_app
from labserver_web.clients.core import CoreClient
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
    ) -> None:
        self.plans = list(plans or [])
        self.servers = list(servers or [])
        self.users = list(users or [])
        self._conflicts = conflicts or {}
        self.calls: list[tuple[str, Any]] = []

    def list_servers(self) -> list[ServerRead]:
        self.calls.append(("list_servers", None))
        return list(self.servers)

    def list_users(self) -> list[UserRead]:
        self.calls.append(("list_users", None))
        return list(self.users)

    def list_plans(
        self,
        *,
        server_id: UUID | None = None,
        owner_id: UUID | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        include_cancelled: bool = False,
    ) -> list[PlanRead]:
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
        selected = [
            plan
            for plan in self.plans
            if (include_cancelled or plan.cancelled_at is None)
            and (server_id is None or plan.server_id == server_id)
        ]
        return selected

    def list_conflicts(self, plan_id: UUID) -> list[PlanConflictRead]:
        return list(self._conflicts.get(plan_id, []))

    def create_plan(self, data: PlanCreate) -> PlanRead:
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
        self.calls.append(("cancel_plan", plan_id))
        return plan_read(
            id=str(plan_id),
            cancelled_at="2026-09-15T10:00:00Z",
            display_state="cancelled",
        )


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


@pytest.fixture
def fake_core() -> FakeCoreClient:
    return FakeCoreClient(
        servers=[
            server_read(),
            server_read(BOB_SERVER_ID, "fwq51", "fwq51"),
        ],
        users=[user_read(ALICE_ID, "alice"), user_read(BOB_ID, "bob")],
    )


@pytest.fixture
def client(fake_core: FakeCoreClient) -> TestClient:
    app = create_app(WebSettings(core_base_url="http://core.test"))
    app.dependency_overrides[get_core_client] = lambda: fake_core
    with TestClient(app) as test_client:
        yield test_client
