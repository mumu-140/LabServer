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
    ManagedServer,
    Reservation,
    ServerCapacity,
    TaskRequest,
    User,
)

from .models import ManagedServerModel, ReservationModel, TaskRequestModel, UserModel


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


class UserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, user_id: UUID) -> User | None:
        model = self._session.get(UserModel, user_id)
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
