from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from labserver_contracts.common import ConflictCertainty, ConflictResource, UserRole
from labserver_contracts.plans import PlanConflictRead, PlanCreate, PlanUpdate
from labserver_core.application.actors import CurrentActor
from labserver_core.application.plan_service import PlanService
from labserver_core.domain.entities import (
    AuditEvent,
    ManagedServer,
    PlanEntry,
    ServerCapacity,
    User,
)
from labserver_core.domain.errors import DomainValidationError, Forbidden, NotFound, ServerDisabled

NOW = datetime(2026, 9, 15, 8, 0, tzinfo=UTC)
START = datetime(2026, 9, 20, 8, 0, tzinfo=UTC)
ADMIN_ID = UUID("00000000-0000-0000-0000-000000000901")
MEMBER_ID = UUID("00000000-0000-0000-0000-000000000902")
OTHER_ID = UUID("00000000-0000-0000-0000-000000000903")
SERVER_ID = UUID("00000000-0000-0000-0000-000000000904")
PLAN_ID = UUID("00000000-0000-0000-0000-000000000905")
AUDIT_ID = UUID("00000000-0000-0000-0000-000000000906")
EXISTING_PLAN_ID = UUID("00000000-0000-0000-0000-000000000907")


class FakeUsers:
    def __init__(self, users: list[User]) -> None:
        self.items = {item.id: item for item in users}

    def get(self, user_id: UUID) -> User | None:
        return self.items.get(user_id)


class FakeServers:
    def __init__(self, servers: list[ManagedServer]) -> None:
        self.items = {server.id: server for server in servers}

    def get(self, server_id: UUID) -> ManagedServer | None:
        return self.items.get(server_id)


class FakePlans:
    def __init__(self, plans: list[PlanEntry] | None = None) -> None:
        self.items: dict[UUID, PlanEntry] = {plan.id: plan for plan in (plans or [])}

    def get(self, plan_id: UUID) -> PlanEntry | None:
        return self.items.get(plan_id)

    def add(self, plan: PlanEntry) -> None:
        self.items[plan.id] = plan

    def save(self, plan: PlanEntry) -> None:
        if plan.id not in self.items:
            raise KeyError(f"Plan {plan.id} does not exist")
        self.items[plan.id] = plan

    def list(
        self,
        *,
        server_id: UUID | None = None,
        owner_id: UUID | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        include_cancelled: bool = False,
    ) -> list[PlanEntry]:
        selected = [
            plan
            for plan in self.items.values()
            if (include_cancelled or plan.cancelled_at is None)
            and (server_id is None or plan.server_id == server_id)
            and (owner_id is None or plan.owner_id == owner_id)
            and (start is None or plan.end_at > start)
            and (end is None or plan.start_at < end)
        ]
        return sorted(selected, key=lambda plan: (plan.start_at, plan.id))


class FakeAudits:
    def __init__(self) -> None:
        self.items: list[AuditEvent] = []

    def add(self, event: AuditEvent) -> None:
        self.items.append(event)


class FakeUow:
    def __init__(
        self,
        *,
        servers: list[ManagedServer] | None = None,
        plans: list[PlanEntry] | None = None,
    ) -> None:
        self.users = FakeUsers(
            [
                User(ADMIN_ID, "admin", "Admin", UserRole.ADMIN, True, NOW, NOW),
                User(MEMBER_ID, "member", "Member", UserRole.MEMBER, True, NOW, NOW),
                User(OTHER_ID, "other", "Other", UserRole.MEMBER, True, NOW, NOW),
            ]
        )
        self.servers = FakeServers(servers if servers is not None else [server()])
        self.plans = FakePlans(plans)
        self.audits = FakeAudits()
        self.commits = 0

    def __enter__(self) -> "FakeUow":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        return None


def server(*, enabled: bool = True, gpu: int = 4) -> ManagedServer:
    return ManagedServer(
        SERVER_ID,
        "fwq10",
        "fwq10",
        enabled,
        ServerCapacity(64, 256.0, gpu),
        NOW,
        NOW,
    )


def service_for(
    uow: FakeUow,
    *,
    clock: Callable[[], datetime] | None = None,
    plan_ids: list[UUID] | None = None,
    audit_ids: list[UUID] | None = None,
) -> PlanService:
    ids = iter(plan_ids or [PLAN_ID])
    audits = iter(audit_ids or [AUDIT_ID])
    return PlanService(
        lambda: uow,
        clock=clock or (lambda: NOW),
        plan_id_factory=lambda: next(ids),
        audit_id_factory=lambda: next(audits),
    )


def plan_create(**overrides: object) -> PlanCreate:
    payload: dict[str, object] = {
        "server_id": SERVER_ID,
        "title": "Poplar assembly",
        "start_at": START,
        "end_at": START + timedelta(hours=2),
    }
    payload.update(overrides)
    return PlanCreate.model_validate(payload)


def existing_plan(**overrides: object) -> PlanEntry:
    values: dict[str, object] = {
        "id": EXISTING_PLAN_ID,
        "owner_id": OTHER_ID,
        "server_id": SERVER_ID,
        "title": "Existing",
        "project": None,
        "start_at": START,
        "end_at": START + timedelta(hours=2),
        "cpu_cores": None,
        "memory_gb": None,
        "gpu_count": None,
        "gpu_ids": None,
        "note": None,
        "cancelled_at": None,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return PlanEntry(**values)


def test_member_creates_plan_with_self_ownership() -> None:
    uow = FakeUow()
    service = service_for(uow)

    created = service.create(CurrentActor(MEMBER_ID, UserRole.MEMBER), plan_create())

    assert created.owner_id == MEMBER_ID
    assert created.id == PLAN_ID
    assert created.display_state == "upcoming"
    assert uow.commits == 1
    assert [event.action for event in uow.audits.items] == ["created"]


def test_create_on_missing_server_raises_not_found() -> None:
    uow = FakeUow(servers=[])
    service = service_for(uow)

    with pytest.raises(NotFound):
        service.create(CurrentActor(MEMBER_ID, UserRole.MEMBER), plan_create())


def test_create_on_disabled_server_raises_server_disabled() -> None:
    uow = FakeUow(servers=[server(enabled=False)])
    service = service_for(uow)

    with pytest.raises(ServerDisabled):
        service.create(CurrentActor(MEMBER_ID, UserRole.MEMBER), plan_create())


def test_create_with_overlapping_plan_is_not_blocked() -> None:
    uow = FakeUow(plans=[existing_plan(gpu_count=4, gpu_ids=(0, 1, 2, 3))])
    service = service_for(uow)

    created = service.create(
        CurrentActor(MEMBER_ID, UserRole.MEMBER),
        plan_create(gpu_count=4, gpu_ids=(0, 1, 2, 3)),
    )

    assert created.id == PLAN_ID
    assert uow.commits == 1


def test_member_can_update_own_plan() -> None:
    owned = existing_plan(owner_id=MEMBER_ID, id=PLAN_ID)
    uow = FakeUow(plans=[owned])
    service = service_for(uow)

    updated = service.update(
        CurrentActor(MEMBER_ID, UserRole.MEMBER),
        PLAN_ID,
        PlanUpdate.model_validate({"title": "Renamed", "note": "moved"}),
    )

    assert updated.title == "Renamed"
    assert updated.note == "moved"
    assert updated.start_at == owned.start_at
    assert uow.commits == 1


def test_member_cannot_update_another_members_plan() -> None:
    uow = FakeUow(plans=[existing_plan()])
    service = service_for(uow)

    with pytest.raises(Forbidden):
        service.update(
            CurrentActor(MEMBER_ID, UserRole.MEMBER),
            EXISTING_PLAN_ID,
            PlanUpdate.model_validate({"title": "Hijack"}),
        )
    assert uow.commits == 0


def test_admin_can_update_any_plan() -> None:
    uow = FakeUow(plans=[existing_plan()])
    service = service_for(uow)

    updated = service.update(
        CurrentActor(ADMIN_ID, UserRole.ADMIN),
        EXISTING_PLAN_ID,
        PlanUpdate.model_validate({"title": "Admin rename"}),
    )

    assert updated.title == "Admin rename"


def test_update_validates_final_interval_after_merge() -> None:
    uow = FakeUow(plans=[existing_plan(owner_id=MEMBER_ID, id=PLAN_ID)])
    service = service_for(uow)

    with pytest.raises(DomainValidationError):
        service.update(
            CurrentActor(MEMBER_ID, UserRole.MEMBER),
            PLAN_ID,
            PlanUpdate.model_validate({"start_at": START + timedelta(hours=3)}),
        )
    assert uow.commits == 0


def test_cancel_sets_cancelled_at_once_and_audits() -> None:
    uow = FakeUow(plans=[existing_plan(owner_id=MEMBER_ID, id=PLAN_ID)])
    service = service_for(uow)

    cancelled = service.cancel(CurrentActor(MEMBER_ID, UserRole.MEMBER), PLAN_ID)

    assert cancelled.cancelled_at == NOW
    assert [event.action for event in uow.audits.items] == ["cancelled"]


def test_cancel_is_idempotent() -> None:
    already_cancelled_at = NOW - timedelta(hours=1)
    uow = FakeUow(
        plans=[existing_plan(owner_id=MEMBER_ID, id=PLAN_ID, cancelled_at=already_cancelled_at)]
    )
    service = service_for(uow)

    cancelled = service.cancel(CurrentActor(MEMBER_ID, UserRole.MEMBER), PLAN_ID)

    assert cancelled.cancelled_at == already_cancelled_at
    assert uow.audits.items == []
    assert uow.commits == 0


def test_cancelled_plans_are_excluded_from_default_list() -> None:
    cancelled = existing_plan(cancelled_at=NOW)
    active = existing_plan(id=UUID("00000000-0000-0000-0000-000000000908"))
    uow = FakeUow(plans=[cancelled, active])
    service = service_for(uow)

    listed = service.list(CurrentActor(MEMBER_ID, UserRole.MEMBER))

    assert [plan.id for plan in listed] == [active.id]
    with_cancelled = service.list(
        CurrentActor(MEMBER_ID, UserRole.MEMBER), include_cancelled=True
    )
    assert {plan.id for plan in with_cancelled} == {cancelled.id, active.id}


def test_list_filters_by_server_and_window() -> None:
    here = existing_plan()
    elsewhere = existing_plan(
        id=UUID("00000000-0000-0000-0000-000000000908"),
        server_id=UUID("00000000-0000-0000-0000-000000000909"),
    )
    uow = FakeUow(plans=[here, elsewhere])
    service = service_for(uow)

    listed = service.list(
        CurrentActor(MEMBER_ID, UserRole.MEMBER),
        server_id=SERVER_ID,
        start=START + timedelta(minutes=30),
        end=START + timedelta(hours=1, minutes=30),
    )

    assert [plan.id for plan in listed] == [here.id]


def test_conflicts_return_advisory_warnings() -> None:
    uow = FakeUow(plans=[existing_plan(gpu_count=1, gpu_ids=(0,))])
    service = service_for(uow)

    candidate = existing_plan(
        id=PLAN_ID,
        owner_id=MEMBER_ID,
        start_at=START + timedelta(minutes=30),
        end_at=START + timedelta(hours=1, minutes=30),
        gpu_count=1,
        gpu_ids=(0,),
    )
    uow.plans.add(candidate)

    conflicts = service.conflicts(CurrentActor(MEMBER_ID, UserRole.MEMBER), PLAN_ID)

    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert isinstance(conflict, PlanConflictRead)
    assert conflict.resource is ConflictResource.GPU_DEVICE
    assert conflict.certainty is ConflictCertainty.CONFIRMED
    assert conflict.conflicting_plan_ids == (EXISTING_PLAN_ID,)


def test_conflicts_for_missing_plan_raise_not_found() -> None:
    uow = FakeUow()
    service = service_for(uow)

    with pytest.raises(NotFound):
        service.conflicts(CurrentActor(MEMBER_ID, UserRole.MEMBER), uuid4())
