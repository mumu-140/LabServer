from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from labserver_contracts.common import (
    ReservationSource,
    ReservationStatus,
    TaskRequestStatus,
    UserRole,
)
from labserver_contracts.requests import TaskRequestCreate, TaskRequestUpdate
from labserver_core.application.actors import CurrentActor
from labserver_core.application.request_service import RequestService
from labserver_core.domain.entities import (
    AuditEvent,
    ManagedServer,
    Reservation,
    ServerCapacity,
    TaskRequest,
    User,
)
from labserver_core.domain.errors import CapacityExceeded, DomainValidationError, Forbidden

NOW = datetime(2026, 9, 15, 8, 0, tzinfo=UTC)
START = datetime(2026, 9, 20, 8, 0, tzinfo=UTC)
ADMIN_ID = UUID("00000000-0000-0000-0000-000000000901")
MEMBER_ID = UUID("00000000-0000-0000-0000-000000000902")
OTHER_ID = UUID("00000000-0000-0000-0000-000000000903")
SERVER_ID = UUID("00000000-0000-0000-0000-000000000904")
REQUEST_ID = UUID("00000000-0000-0000-0000-000000000905")
RESERVATION_ID = UUID("00000000-0000-0000-0000-000000000906")
AUDIT_ID = UUID("00000000-0000-0000-0000-000000000907")
EXISTING_RESERVATION_ID = UUID("00000000-0000-0000-0000-000000000908")


class FakeUsers:
    def __init__(self, users: list[User]) -> None:
        self.items = {item.id: item for item in users}

    def get(self, user_id: UUID) -> User | None:
        return self.items.get(user_id)


class FakeServers:
    def __init__(self, server: ManagedServer) -> None:
        self.server = server

    def get(self, server_id: UUID) -> ManagedServer | None:
        return self.server if server_id == self.server.id else None


class FakeRequests:
    def __init__(self, requests: list[TaskRequest] | None = None) -> None:
        self.items = {item.id: item for item in requests or []}

    def get(self, request_id: UUID) -> TaskRequest | None:
        return self.items.get(request_id)

    def add(self, task_request: TaskRequest) -> None:
        self.items[task_request.id] = task_request

    def save(self, task_request: TaskRequest) -> None:
        self.items[task_request.id] = task_request

    def list_for_user(self, user_id: UUID) -> list[TaskRequest]:
        return [item for item in self.items.values() if item.requester_id == user_id]

    def list_all(self) -> list[TaskRequest]:
        return list(self.items.values())


class FakeReservations:
    def __init__(self, reservations: list[Reservation] | None = None) -> None:
        self.items = {item.id: item for item in reservations or []}

    def get_by_request_id(self, request_id: UUID) -> Reservation | None:
        return next((item for item in self.items.values() if item.request_id == request_id), None)

    def add(self, reservation: Reservation) -> None:
        self.items[reservation.id] = reservation

    def list_for_server(
        self,
        server_id: UUID,
        start: datetime,
        end: datetime,
    ) -> list[Reservation]:
        return [
            item
            for item in self.items.values()
            if item.server_id == server_id and item.start_at < end and item.end_at > start
        ]

    def list_window(self, start: datetime, end: datetime) -> list[Reservation]:
        return [item for item in self.items.values() if item.start_at < end and item.end_at > start]


class FakeAudits:
    def __init__(self) -> None:
        self.items: list[AuditEvent] = []

    def add(self, event: AuditEvent) -> None:
        self.items.append(event)


class FakeUow:
    def __init__(
        self,
        *,
        server: ManagedServer,
        requests: list[TaskRequest] | None = None,
        reservations: list[Reservation] | None = None,
    ) -> None:
        self.users = FakeUsers(
            [
                user(ADMIN_ID, "admin", UserRole.ADMIN),
                user(MEMBER_ID, "member", UserRole.MEMBER),
                user(OTHER_ID, "other", UserRole.MEMBER),
            ]
        )
        self.servers = FakeServers(server)
        self.requests = FakeRequests(requests)
        self.reservations = FakeReservations(reservations)
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


def user(user_id: UUID, username: str, role: UserRole) -> User:
    return User(user_id, username, username.title(), role, True, NOW, NOW)


def server(*, enabled: bool = True, cpu: int = 64, gpu: int = 4) -> ManagedServer:
    return ManagedServer(
        SERVER_ID,
        "fwq10",
        "fwq10",
        enabled,
        ServerCapacity(cpu, 256.0, gpu),
        NOW,
        NOW,
    )


def request(status: TaskRequestStatus = TaskRequestStatus.DRAFT) -> TaskRequest:
    return TaskRequest(
        REQUEST_ID,
        MEMBER_ID,
        "Poplar assembly",
        "Populus",
        SERVER_ID,
        START,
        120,
        32,
        128.0,
        2,
        (0, 1),
        None,
        status,
        NOW,
        NOW,
    )


def request_payload(*, cpu: int = 32) -> TaskRequestCreate:
    return TaskRequestCreate.model_validate(
        {
            "title": "Poplar assembly",
            "project": "Populus",
            "preferred_server_id": str(SERVER_ID),
            "planned_start": START.isoformat(),
            "planned_duration_minutes": 120,
            "requested_cpu_cores": cpu,
            "requested_memory_gb": 128.0,
            "requested_gpu_count": 2,
            "preferred_gpu_ids": [0, 1],
        }
    )


def existing_conflicting_reservation() -> Reservation:
    return Reservation(
        EXISTING_RESERVATION_ID,
        None,
        OTHER_ID,
        SERVER_ID,
        "Existing",
        START,
        START + timedelta(hours=2),
        40,
        64.0,
        2,
        (0, 1),
        ReservationStatus.PLANNED,
        ReservationSource.ADMIN,
        NOW,
        NOW,
    )


def service_for(uow: FakeUow) -> RequestService:
    return RequestService(
        lambda: uow,
        clock=lambda: NOW,
        request_id_factory=lambda: REQUEST_ID,
        reservation_id_factory=lambda: RESERVATION_ID,
        audit_id_factory=lambda: AUDIT_ID,
    )


def test_member_creates_own_draft() -> None:
    uow = FakeUow(server=server())
    service = service_for(uow)

    created = service.create_request(CurrentActor(MEMBER_ID, UserRole.MEMBER), request_payload())

    assert created.id == REQUEST_ID
    assert created.requester_id == MEMBER_ID
    assert created.status is TaskRequestStatus.DRAFT
    assert uow.requests.get(REQUEST_ID) == created
    assert uow.commits == 1


def test_member_cannot_create_draft_for_another_user() -> None:
    uow = FakeUow(server=server())
    service = service_for(uow)

    with pytest.raises(Forbidden):
        service.create_request(
            CurrentActor(MEMBER_ID, UserRole.MEMBER),
            request_payload(),
            requester_id=OTHER_ID,
        )

    assert uow.commits == 0


def test_owner_can_edit_draft_but_submitted_request_cannot_be_edited() -> None:
    draft = request()
    uow = FakeUow(server=server(), requests=[draft])
    service = service_for(uow)
    actor = CurrentActor(MEMBER_ID, UserRole.MEMBER)

    updated = service.update_draft(actor, REQUEST_ID, TaskRequestUpdate(title="New title"))
    assert updated.title == "New title"

    uow.requests.save(request(TaskRequestStatus.SUBMITTED))
    with pytest.raises(DomainValidationError):
        service.update_draft(actor, REQUEST_ID, TaskRequestUpdate(title="Should fail"))


def test_submit_validates_server_capacity() -> None:
    uow = FakeUow(server=server(cpu=16), requests=[request()])
    service = service_for(uow)

    with pytest.raises(CapacityExceeded):
        service.submit_request(CurrentActor(MEMBER_ID, UserRole.MEMBER), REQUEST_ID)


def test_admin_rejection_records_actor_and_audit_event() -> None:
    submitted = request(TaskRequestStatus.SUBMITTED)
    uow = FakeUow(server=server(), requests=[submitted])
    service = service_for(uow)

    rejected = service.reject_request(CurrentActor(ADMIN_ID, UserRole.ADMIN), REQUEST_ID)

    assert rejected.status is TaskRequestStatus.REJECTED
    assert rejected.status_changed_by == ADMIN_ID
    assert len(uow.audits.items) == 1
    assert uow.audits.items[0].action == "request_rejected"
    assert uow.audits.items[0].actor_id == ADMIN_ID


def test_admin_approval_creates_one_reservation_and_is_idempotent() -> None:
    submitted = request(TaskRequestStatus.SUBMITTED)
    uow = FakeUow(server=server(), requests=[submitted])
    service = service_for(uow)
    actor = CurrentActor(ADMIN_ID, UserRole.ADMIN)

    created = service.approve_request(actor, REQUEST_ID)
    repeated = service.approve_request(actor, REQUEST_ID)

    assert created.id == RESERVATION_ID
    assert repeated.id == created.id
    assert created.request_id == REQUEST_ID
    assert created.start_at == START
    assert created.end_at == START + timedelta(minutes=120)
    assert len(uow.reservations.items) == 1
    assert uow.requests.get(REQUEST_ID).status is TaskRequestStatus.APPROVED
    assert uow.commits == 1


def test_conflict_warning_does_not_block_approval() -> None:
    submitted = request(TaskRequestStatus.SUBMITTED)
    uow = FakeUow(
        server=server(),
        requests=[submitted],
        reservations=[existing_conflicting_reservation()],
    )
    service = service_for(uow)

    preview = service.preview_request_conflicts(
        CurrentActor(MEMBER_ID, UserRole.MEMBER), REQUEST_ID
    )
    approved = service.approve_request(CurrentActor(ADMIN_ID, UserRole.ADMIN), REQUEST_ID)

    assert preview
    assert approved.id == RESERVATION_ID
    assert uow.requests.get(REQUEST_ID).status is TaskRequestStatus.APPROVED
    assert uow.audits.items[-1].details == {"conflict_count": len(preview)}


def test_member_lists_only_own_requests_while_admin_lists_all() -> None:
    own = request()
    other = TaskRequest(
        UUID("00000000-0000-0000-0000-000000000909"),
        OTHER_ID,
        "Other task",
        None,
        SERVER_ID,
        START,
        60,
        1,
        None,
        0,
        None,
        None,
        TaskRequestStatus.DRAFT,
        NOW,
        NOW,
    )
    uow = FakeUow(server=server(), requests=[own, other])
    service = service_for(uow)

    member_items = service.list_requests(CurrentActor(MEMBER_ID, UserRole.MEMBER))
    admin_items = service.list_requests(CurrentActor(ADMIN_ID, UserRole.ADMIN))

    assert [item.id for item in member_items] == [REQUEST_ID]
    assert {item.id for item in admin_items} == {REQUEST_ID, other.id}
