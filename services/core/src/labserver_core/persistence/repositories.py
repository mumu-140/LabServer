from datetime import UTC, datetime
from uuid import UUID

from labserver_contracts.common import (
    ReservationSource,
    ReservationStatus,
    TaskRequestStatus,
    UserRole,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from labserver_core.domain.entities import (
    AuditEvent,
    ManagedServer,
    PlanEntry,
    Reservation,
    ServerCapacity,
    TaskRequest,
    User,
)

from .models import (
    AuditEventModel,
    ManagedServerModel,
    PlanEntryModel,
    ReservationModel,
    TaskRequestModel,
    UserModel,
)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _user_from_model(model: UserModel) -> User:
    return User(
        id=model.id,
        username=model.username,
        display_name=model.display_name,
        role=UserRole(model.role),
        enabled=model.enabled,
        created_at=_as_utc(model.created_at),
        updated_at=_as_utc(model.updated_at),
    )


def _server_from_model(model: ManagedServerModel) -> ManagedServer:
    return ManagedServer(
        id=model.id,
        key=model.key,
        display_name=model.display_name,
        enabled=model.enabled,
        capacity=ServerCapacity(model.cpu_cores, model.memory_gb, model.gpu_count),
        created_at=_as_utc(model.created_at),
        updated_at=_as_utc(model.updated_at),
    )


def _request_from_model(model: TaskRequestModel) -> TaskRequest:
    return TaskRequest(
        id=model.id,
        requester_id=model.requester_id,
        title=model.title,
        project=model.project,
        preferred_server_id=model.preferred_server_id,
        planned_start=_as_utc(model.planned_start),
        planned_duration_minutes=model.planned_duration_minutes,
        requested_cpu_cores=model.requested_cpu_cores,
        requested_memory_gb=model.requested_memory_gb,
        requested_gpu_count=model.requested_gpu_count,
        preferred_gpu_ids=(
            tuple(model.preferred_gpu_ids) if model.preferred_gpu_ids is not None else None
        ),
        note=model.note,
        status=TaskRequestStatus(model.status),
        created_at=_as_utc(model.created_at),
        updated_at=_as_utc(model.updated_at),
        status_changed_by=model.status_changed_by,
    )


def _reservation_from_model(model: ReservationModel) -> Reservation:
    return Reservation(
        id=model.id,
        request_id=model.request_id,
        owner_id=model.owner_id,
        server_id=model.server_id,
        title=model.title,
        start_at=_as_utc(model.start_at),
        end_at=_as_utc(model.end_at),
        cpu_cores=model.cpu_cores,
        memory_gb=model.memory_gb,
        gpu_count=model.gpu_count,
        gpu_ids=tuple(model.gpu_ids) if model.gpu_ids is not None else None,
        status=ReservationStatus(model.status),
        source=ReservationSource(model.source),
        created_at=_as_utc(model.created_at),
        updated_at=_as_utc(model.updated_at),
    )


def _audit_from_model(model: AuditEventModel) -> AuditEvent:
    return AuditEvent(
        id=model.id,
        entity_type=model.entity_type,
        entity_id=model.entity_id,
        action=model.action,
        actor_id=model.actor_id,
        occurred_at=_as_utc(model.occurred_at),
        details=model.details,
    )


class UserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, user_id: UUID) -> User | None:
        model = self._session.get(UserModel, user_id)
        return _user_from_model(model) if model is not None else None

    def get_by_username(self, username: str) -> User | None:
        model = self._session.scalar(select(UserModel).where(UserModel.username == username))
        return _user_from_model(model) if model is not None else None

    def add(self, user: User) -> None:
        self._session.add(
            UserModel(
                id=user.id,
                username=user.username,
                display_name=user.display_name,
                role=user.role.value,
                enabled=user.enabled,
                created_at=user.created_at,
                updated_at=user.updated_at,
            )
        )

    def list_all(self) -> list[User]:
        models = self._session.scalars(select(UserModel).order_by(UserModel.username)).all()
        return [_user_from_model(model) for model in models]


class ServerRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, server_id: UUID) -> ManagedServer | None:
        model = self._session.get(ManagedServerModel, server_id)
        return _server_from_model(model) if model is not None else None

    def get_by_key(self, key: str) -> ManagedServer | None:
        model = self._session.scalar(
            select(ManagedServerModel).where(ManagedServerModel.key == key)
        )
        return _server_from_model(model) if model is not None else None

    def add(self, server: ManagedServer) -> None:
        self._session.add(
            ManagedServerModel(
                id=server.id,
                key=server.key,
                display_name=server.display_name,
                enabled=server.enabled,
                cpu_cores=server.capacity.cpu_cores,
                memory_gb=server.capacity.memory_gb,
                gpu_count=server.capacity.gpu_count,
                created_at=server.created_at,
                updated_at=server.updated_at,
            )
        )

    def save(self, server: ManagedServer) -> None:
        model = self._session.get(ManagedServerModel, server.id)
        if model is None:
            raise KeyError(f"Server {server.id} does not exist")
        model.display_name = server.display_name
        model.enabled = server.enabled
        model.cpu_cores = server.capacity.cpu_cores
        model.memory_gb = server.capacity.memory_gb
        model.gpu_count = server.capacity.gpu_count
        model.updated_at = server.updated_at

    def list_all(self) -> list[ManagedServer]:
        models = self._session.scalars(
            select(ManagedServerModel).order_by(ManagedServerModel.key)
        ).all()
        return [_server_from_model(model) for model in models]


class RequestRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, request_id: UUID) -> TaskRequest | None:
        model = self._session.get(TaskRequestModel, request_id)
        return _request_from_model(model) if model is not None else None

    def add(self, task_request: TaskRequest) -> None:
        self._session.add(
            TaskRequestModel(
                id=task_request.id,
                title=task_request.title,
                requester_id=task_request.requester_id,
                project=task_request.project,
                preferred_server_id=task_request.preferred_server_id,
                planned_start=task_request.planned_start,
                planned_duration_minutes=task_request.planned_duration_minutes,
                requested_cpu_cores=task_request.requested_cpu_cores,
                requested_memory_gb=task_request.requested_memory_gb,
                requested_gpu_count=task_request.requested_gpu_count,
                preferred_gpu_ids=(
                    list(task_request.preferred_gpu_ids)
                    if task_request.preferred_gpu_ids is not None
                    else None
                ),
                note=task_request.note,
                status=task_request.status.value,
                status_changed_by=task_request.status_changed_by,
                created_at=task_request.created_at,
                updated_at=task_request.updated_at,
            )
        )

    def save(self, task_request: TaskRequest) -> None:
        model = self._session.get(TaskRequestModel, task_request.id)
        if model is None:
            raise KeyError(f"Request {task_request.id} does not exist")
        model.title = task_request.title
        model.project = task_request.project
        model.preferred_server_id = task_request.preferred_server_id
        model.planned_start = task_request.planned_start
        model.planned_duration_minutes = task_request.planned_duration_minutes
        model.requested_cpu_cores = task_request.requested_cpu_cores
        model.requested_memory_gb = task_request.requested_memory_gb
        model.requested_gpu_count = task_request.requested_gpu_count
        model.preferred_gpu_ids = (
            list(task_request.preferred_gpu_ids)
            if task_request.preferred_gpu_ids is not None
            else None
        )
        model.note = task_request.note
        model.status = task_request.status.value
        model.status_changed_by = task_request.status_changed_by
        model.updated_at = task_request.updated_at

    def list_for_user(self, user_id: UUID) -> list[TaskRequest]:
        models = self._session.scalars(
            select(TaskRequestModel)
            .where(TaskRequestModel.requester_id == user_id)
            .order_by(TaskRequestModel.created_at, TaskRequestModel.id)
        ).all()
        return [_request_from_model(model) for model in models]

    def list_all(self) -> list[TaskRequest]:
        models = self._session.scalars(
            select(TaskRequestModel).order_by(TaskRequestModel.created_at, TaskRequestModel.id)
        ).all()
        return [_request_from_model(model) for model in models]


class ReservationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_request_id(self, request_id: UUID) -> Reservation | None:
        model = self._session.scalar(
            select(ReservationModel).where(ReservationModel.request_id == request_id)
        )
        return _reservation_from_model(model) if model is not None else None

    def add(self, reservation: Reservation) -> None:
        self._session.add(
            ReservationModel(
                id=reservation.id,
                request_id=reservation.request_id,
                owner_id=reservation.owner_id,
                server_id=reservation.server_id,
                title=reservation.title,
                start_at=reservation.start_at,
                end_at=reservation.end_at,
                cpu_cores=reservation.cpu_cores,
                memory_gb=reservation.memory_gb,
                gpu_count=reservation.gpu_count,
                gpu_ids=list(reservation.gpu_ids) if reservation.gpu_ids is not None else None,
                status=reservation.status.value,
                source=reservation.source.value,
                created_at=reservation.created_at,
                updated_at=reservation.updated_at,
            )
        )

    def list_for_server(
        self, server_id: UUID, start: datetime, end: datetime
    ) -> list[Reservation]:
        models = self._session.scalars(
            select(ReservationModel)
            .where(
                ReservationModel.server_id == server_id,
                ReservationModel.start_at < end,
                ReservationModel.end_at > start,
            )
            .order_by(ReservationModel.start_at, ReservationModel.id)
        ).all()
        return [_reservation_from_model(model) for model in models]

    def list_window(self, start: datetime, end: datetime) -> list[Reservation]:
        models = self._session.scalars(
            select(ReservationModel)
            .where(ReservationModel.start_at < end, ReservationModel.end_at > start)
            .order_by(ReservationModel.start_at, ReservationModel.id)
        ).all()
        return [_reservation_from_model(model) for model in models]


class AuditRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, event: AuditEvent) -> None:
        self._session.add(
            AuditEventModel(
                id=event.id,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                action=event.action,
                actor_id=event.actor_id,
                occurred_at=event.occurred_at,
                details=event.details,
            )
        )

    def list_for_entity(self, entity_type: str, entity_id: UUID) -> list[AuditEvent]:
        models = self._session.scalars(
            select(AuditEventModel)
            .where(
                AuditEventModel.entity_type == entity_type,
                AuditEventModel.entity_id == entity_id,
            )
            .order_by(AuditEventModel.occurred_at, AuditEventModel.id)
        ).all()
        return [_audit_from_model(model) for model in models]


def _plan_from_model(model: PlanEntryModel) -> PlanEntry:
    return PlanEntry(
        id=model.id,
        owner_id=model.owner_id,
        server_id=model.server_id,
        title=model.title,
        project=model.project,
        start_at=_as_utc(model.start_at),
        end_at=_as_utc(model.end_at),
        cpu_cores=model.cpu_cores,
        memory_gb=model.memory_gb,
        gpu_count=model.gpu_count,
        gpu_ids=tuple(model.gpu_ids) if model.gpu_ids is not None else None,
        note=model.note,
        cancelled_at=_as_utc(model.cancelled_at) if model.cancelled_at is not None else None,
        created_at=_as_utc(model.created_at),
        updated_at=_as_utc(model.updated_at),
    )


class PlanRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, plan_id: UUID) -> PlanEntry | None:
        model = self._session.get(PlanEntryModel, plan_id)
        return _plan_from_model(model) if model is not None else None

    def add(self, plan: PlanEntry) -> None:
        self._session.add(
            PlanEntryModel(
                id=plan.id,
                owner_id=plan.owner_id,
                server_id=plan.server_id,
                title=plan.title,
                project=plan.project,
                start_at=plan.start_at,
                end_at=plan.end_at,
                cpu_cores=plan.cpu_cores,
                memory_gb=plan.memory_gb,
                gpu_count=plan.gpu_count,
                gpu_ids=list(plan.gpu_ids) if plan.gpu_ids is not None else None,
                note=plan.note,
                cancelled_at=plan.cancelled_at,
                created_at=plan.created_at,
                updated_at=plan.updated_at,
            )
        )

    def save(self, plan: PlanEntry) -> None:
        model = self._session.get(PlanEntryModel, plan.id)
        if model is None:
            raise KeyError(f"Plan {plan.id} does not exist")
        model.owner_id = plan.owner_id
        model.server_id = plan.server_id
        model.title = plan.title
        model.project = plan.project
        model.start_at = plan.start_at
        model.end_at = plan.end_at
        model.cpu_cores = plan.cpu_cores
        model.memory_gb = plan.memory_gb
        model.gpu_count = plan.gpu_count
        model.gpu_ids = list(plan.gpu_ids) if plan.gpu_ids is not None else None
        model.note = plan.note
        model.cancelled_at = plan.cancelled_at
        model.updated_at = plan.updated_at

    def list(
        self,
        *,
        server_id: UUID | None = None,
        owner_id: UUID | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        include_cancelled: bool = False,
    ) -> list[PlanEntry]:
        conditions = []
        if server_id is not None:
            conditions.append(PlanEntryModel.server_id == server_id)
        if owner_id is not None:
            conditions.append(PlanEntryModel.owner_id == owner_id)
        if start is not None:
            # Half-open window: a plan counts when it ends after the query start.
            conditions.append(PlanEntryModel.end_at > start)
        if end is not None:
            # ...and starts before the query end; containment is not required.
            conditions.append(PlanEntryModel.start_at < end)
        if not include_cancelled:
            conditions.append(PlanEntryModel.cancelled_at.is_(None))

        stmt = select(PlanEntryModel)
        if conditions:
            stmt = stmt.where(*conditions)
        stmt = stmt.order_by(PlanEntryModel.start_at, PlanEntryModel.id)
        models = self._session.scalars(stmt).all()
        return [_plan_from_model(model) for model in models]
