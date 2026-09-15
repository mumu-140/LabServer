from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from labserver_contracts.common import (
    ReservationSource,
    ReservationStatus,
    TaskRequestStatus,
    UserRole,
)
from labserver_contracts.requests import TaskRequestCreate, TaskRequestUpdate

from labserver_core.domain.conflicts import Conflict, evaluate_conflicts
from labserver_core.domain.entities import AuditEvent, ManagedServer, Reservation, TaskRequest
from labserver_core.domain.errors import DomainValidationError, Forbidden, NotFound
from labserver_core.domain.transitions import transition_request

from .actors import CurrentActor, require_active_actor, require_admin, require_self_or_admin
from .ports import UnitOfWork, UnitOfWorkFactory


def _utc_now() -> datetime:
    return datetime.now(UTC)


class RequestService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        *,
        clock: Callable[[], datetime] = _utc_now,
        request_id_factory: Callable[[], UUID] = uuid4,
        reservation_id_factory: Callable[[], UUID] = uuid4,
        audit_id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._request_id_factory = request_id_factory
        self._reservation_id_factory = reservation_id_factory
        self._audit_id_factory = audit_id_factory

    def _active_actor(self, uow: UnitOfWork, actor: CurrentActor) -> None:
        require_active_actor(actor, uow.users.get(actor.user_id))

    def _request_for_actor(
        self,
        uow: UnitOfWork,
        actor: CurrentActor,
        request_id: UUID,
    ) -> TaskRequest:
        task_request = uow.requests.get(request_id)
        if task_request is None:
            raise NotFound(f"Request {request_id} was not found")
        require_self_or_admin(actor, task_request.requester_id)
        return task_request

    def _server_for_request(self, uow: UnitOfWork, task_request: TaskRequest) -> ManagedServer:
        server = uow.servers.get(task_request.preferred_server_id)
        if server is None:
            raise NotFound(f"Server {task_request.preferred_server_id} was not found")
        return server

    def _audit(
        self,
        uow: UnitOfWork,
        *,
        task_request: TaskRequest,
        action: str,
        actor: CurrentActor,
        occurred_at: datetime,
        details: dict[str, object] | None = None,
    ) -> None:
        uow.audits.add(
            AuditEvent(
                id=self._audit_id_factory(),
                entity_type="task_request",
                entity_id=task_request.id,
                action=action,
                actor_id=actor.user_id,
                occurred_at=occurred_at,
                details=details,
            )
        )

    def create_request(
        self,
        actor: CurrentActor,
        data: TaskRequestCreate,
        *,
        requester_id: UUID | None = None,
    ) -> TaskRequest:
        with self._uow_factory() as uow:
            self._active_actor(uow, actor)
            owner_id = requester_id or actor.user_id
            require_self_or_admin(actor, owner_id)
            owner = uow.users.get(owner_id)
            if owner is None:
                raise NotFound(f"User {owner_id} was not found")
            if not owner.enabled:
                raise Forbidden("Cannot create a request for a disabled user")
            if uow.servers.get(data.preferred_server_id) is None:
                raise NotFound(f"Server {data.preferred_server_id} was not found")

            now = self._clock()
            task_request = TaskRequest(
                id=self._request_id_factory(),
                requester_id=owner_id,
                title=data.title,
                project=data.project,
                preferred_server_id=data.preferred_server_id,
                planned_start=data.planned_start,
                planned_duration_minutes=data.planned_duration_minutes,
                requested_cpu_cores=data.requested_cpu_cores,
                requested_memory_gb=data.requested_memory_gb,
                requested_gpu_count=data.requested_gpu_count,
                preferred_gpu_ids=(
                    tuple(data.preferred_gpu_ids) if data.preferred_gpu_ids is not None else None
                ),
                note=data.note,
                status=TaskRequestStatus.DRAFT,
                created_at=now,
                updated_at=now,
            )
            uow.requests.add(task_request)
            uow.commit()
            return task_request

    def list_requests(self, actor: CurrentActor) -> list[TaskRequest]:
        with self._uow_factory() as uow:
            self._active_actor(uow, actor)
            if actor.role is UserRole.ADMIN:
                return uow.requests.list_all()
            return uow.requests.list_for_user(actor.user_id)

    def get_request(self, actor: CurrentActor, request_id: UUID) -> TaskRequest:
        with self._uow_factory() as uow:
            self._active_actor(uow, actor)
            return self._request_for_actor(uow, actor, request_id)

    def update_draft(
        self,
        actor: CurrentActor,
        request_id: UUID,
        data: TaskRequestUpdate,
    ) -> TaskRequest:
        with self._uow_factory() as uow:
            self._active_actor(uow, actor)
            current = self._request_for_actor(uow, actor, request_id)
            if current.status is not TaskRequestStatus.DRAFT:
                raise DomainValidationError("Only draft requests can be edited")

            fields = data.model_fields_set
            required_fields = (
                "title",
                "preferred_server_id",
                "planned_start",
                "planned_duration_minutes",
                "requested_cpu_cores",
                "requested_gpu_count",
            )
            for name in required_fields:
                if name in fields and getattr(data, name) is None:
                    raise DomainValidationError(f"{name} cannot be cleared")

            updated = replace(
                current,
                title=data.title if "title" in fields and data.title is not None else current.title,
                project=data.project if "project" in fields else current.project,
                preferred_server_id=(
                    data.preferred_server_id
                    if "preferred_server_id" in fields and data.preferred_server_id is not None
                    else current.preferred_server_id
                ),
                planned_start=(
                    data.planned_start
                    if "planned_start" in fields and data.planned_start is not None
                    else current.planned_start
                ),
                planned_duration_minutes=(
                    data.planned_duration_minutes
                    if "planned_duration_minutes" in fields
                    and data.planned_duration_minutes is not None
                    else current.planned_duration_minutes
                ),
                requested_cpu_cores=(
                    data.requested_cpu_cores
                    if "requested_cpu_cores" in fields and data.requested_cpu_cores is not None
                    else current.requested_cpu_cores
                ),
                requested_memory_gb=(
                    data.requested_memory_gb
                    if "requested_memory_gb" in fields
                    else current.requested_memory_gb
                ),
                requested_gpu_count=(
                    data.requested_gpu_count
                    if "requested_gpu_count" in fields and data.requested_gpu_count is not None
                    else current.requested_gpu_count
                ),
                preferred_gpu_ids=(
                    tuple(data.preferred_gpu_ids)
                    if "preferred_gpu_ids" in fields and data.preferred_gpu_ids is not None
                    else (None if "preferred_gpu_ids" in fields else current.preferred_gpu_ids)
                ),
                note=data.note if "note" in fields else current.note,
                updated_at=self._clock(),
            )
            if (
                updated.preferred_gpu_ids is not None
                and len(updated.preferred_gpu_ids) != updated.requested_gpu_count
            ):
                raise DomainValidationError(
                    "requested_gpu_count must equal the number of preferred GPU IDs"
                )
            if uow.servers.get(updated.preferred_server_id) is None:
                raise NotFound(f"Server {updated.preferred_server_id} was not found")

            uow.requests.save(updated)
            uow.commit()
            return updated

    def submit_request(
        self,
        actor: CurrentActor,
        request_id: UUID,
        *,
        allow_capacity_override: bool = False,
    ) -> TaskRequest:
        with self._uow_factory() as uow:
            self._active_actor(uow, actor)
            current = self._request_for_actor(uow, actor, request_id)
            server = self._server_for_request(uow, current)
            transitioned = transition_request(
                current,
                TaskRequestStatus.SUBMITTED,
                actor.role,
                server=server,
                allow_capacity_override=allow_capacity_override,
            )
            now = self._clock()
            submitted = replace(
                transitioned,
                status_changed_by=actor.user_id,
                updated_at=now,
            )
            uow.requests.save(submitted)
            self._audit(
                uow,
                task_request=submitted,
                action="request_submitted",
                actor=actor,
                occurred_at=now,
            )
            uow.commit()
            return submitted

    def cancel_request(self, actor: CurrentActor, request_id: UUID) -> TaskRequest:
        with self._uow_factory() as uow:
            self._active_actor(uow, actor)
            current = self._request_for_actor(uow, actor, request_id)
            server = self._server_for_request(uow, current)
            transitioned = transition_request(
                current,
                TaskRequestStatus.CANCELLED,
                actor.role,
                server=server,
            )
            now = self._clock()
            cancelled = replace(
                transitioned,
                status_changed_by=actor.user_id,
                updated_at=now,
            )
            uow.requests.save(cancelled)
            self._audit(
                uow,
                task_request=cancelled,
                action="request_cancelled",
                actor=actor,
                occurred_at=now,
            )
            uow.commit()
            return cancelled

    def reject_request(self, actor: CurrentActor, request_id: UUID) -> TaskRequest:
        with self._uow_factory() as uow:
            self._active_actor(uow, actor)
            require_admin(actor)
            current = self._request_for_actor(uow, actor, request_id)
            server = self._server_for_request(uow, current)
            transitioned = transition_request(
                current,
                TaskRequestStatus.REJECTED,
                actor.role,
                server=server,
            )
            now = self._clock()
            rejected = replace(
                transitioned,
                status_changed_by=actor.user_id,
                updated_at=now,
            )
            uow.requests.save(rejected)
            self._audit(
                uow,
                task_request=rejected,
                action="request_rejected",
                actor=actor,
                occurred_at=now,
            )
            uow.commit()
            return rejected

    def _reservation_candidate(
        self,
        task_request: TaskRequest,
        *,
        reservation_id: UUID,
        now: datetime,
    ) -> Reservation:
        return Reservation(
            id=reservation_id,
            request_id=task_request.id,
            owner_id=task_request.requester_id,
            server_id=task_request.preferred_server_id,
            title=task_request.title,
            start_at=task_request.planned_start,
            end_at=task_request.planned_start
            + timedelta(minutes=task_request.planned_duration_minutes),
            cpu_cores=task_request.requested_cpu_cores,
            memory_gb=task_request.requested_memory_gb,
            gpu_count=task_request.requested_gpu_count,
            gpu_ids=task_request.preferred_gpu_ids,
            status=ReservationStatus.PLANNED,
            source=ReservationSource.REQUEST,
            created_at=now,
            updated_at=now,
        )

    def _conflicts(
        self,
        uow: UnitOfWork,
        task_request: TaskRequest,
        server: ManagedServer,
        *,
        candidate_id: UUID,
        now: datetime,
    ) -> list[Conflict]:
        candidate = self._reservation_candidate(
            task_request,
            reservation_id=candidate_id,
            now=now,
        )
        existing = uow.reservations.list_for_server(
            server.id,
            candidate.start_at,
            candidate.end_at,
        )
        return evaluate_conflicts(candidate, existing, server.capacity)

    def preview_request_conflicts(
        self,
        actor: CurrentActor,
        request_id: UUID,
    ) -> list[Conflict]:
        with self._uow_factory() as uow:
            self._active_actor(uow, actor)
            task_request = self._request_for_actor(uow, actor, request_id)
            server = self._server_for_request(uow, task_request)
            return self._conflicts(
                uow,
                task_request,
                server,
                candidate_id=UUID(int=0),
                now=self._clock(),
            )

    def approve_request(self, actor: CurrentActor, request_id: UUID) -> Reservation:
        with self._uow_factory() as uow:
            self._active_actor(uow, actor)
            require_admin(actor)
            current = self._request_for_actor(uow, actor, request_id)

            if current.status is TaskRequestStatus.APPROVED:
                existing = uow.reservations.get_by_request_id(current.id)
                if existing is None:
                    raise DomainValidationError(
                        "Approved request has no corresponding reservation"
                    )
                return existing

            server = self._server_for_request(uow, current)
            transitioned = transition_request(
                current,
                TaskRequestStatus.APPROVED,
                actor.role,
                server=server,
            )
            now = self._clock()
            approved = replace(
                transitioned,
                status_changed_by=actor.user_id,
                updated_at=now,
            )
            reservation = self._reservation_candidate(
                approved,
                reservation_id=self._reservation_id_factory(),
                now=now,
            )
            existing_reservations = uow.reservations.list_for_server(
                server.id,
                reservation.start_at,
                reservation.end_at,
            )
            conflicts = evaluate_conflicts(
                reservation,
                existing_reservations,
                server.capacity,
            )

            uow.requests.save(approved)
            uow.reservations.add(reservation)
            self._audit(
                uow,
                task_request=approved,
                action="request_approved",
                actor=actor,
                occurred_at=now,
                details={"conflict_count": len(conflicts)},
            )
            uow.commit()
            return reservation
