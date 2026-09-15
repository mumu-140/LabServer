import builtins
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from labserver_contracts.plans import (
    PlanConflictRead,
    PlanCreate,
    PlanRead,
    PlanUpdate,
    validate_plan_window,
)

from labserver_core.domain.conflicts import evaluate_plan_conflicts
from labserver_core.domain.entities import (
    AuditEvent,
    PlanEntry,
    ServerCapacity,
    plan_display_state,
)
from labserver_core.domain.errors import DomainValidationError, NotFound, ServerDisabled

from .actors import CurrentActor, require_active_actor, require_self_or_admin
from .ports import UnitOfWork, UnitOfWorkFactory


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PlanService:
    """Published-intent planning: create, read, update, cancel, advisory conflicts."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        *,
        clock: Callable[[], datetime] = _utc_now,
        plan_id_factory: Callable[[], UUID] = uuid4,
        audit_id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._plan_id_factory = plan_id_factory
        self._audit_id_factory = audit_id_factory

    def _active_actor(self, uow: UnitOfWork, actor: CurrentActor) -> None:
        require_active_actor(actor, uow.users.get(actor.user_id))

    def _plan_or_not_found(self, uow: UnitOfWork, plan_id: UUID) -> PlanEntry:
        plan = uow.plans.get(plan_id)
        if plan is None:
            raise NotFound(f"Plan {plan_id} does not exist")
        return plan

    def _read(self, plan: PlanEntry, now: datetime) -> PlanRead:
        return PlanRead(
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
            gpu_ids=plan.gpu_ids,
            note=plan.note,
            cancelled_at=plan.cancelled_at,
            created_at=plan.created_at,
            updated_at=plan.updated_at,
            display_state=plan_display_state(plan, now),
        )

    def _audit(
        self, uow: UnitOfWork, actor: CurrentActor, action: str, plan: PlanEntry, now: datetime
    ) -> None:
        uow.audits.add(
            AuditEvent(
                id=self._audit_id_factory(),
                entity_type="plan_entry",
                entity_id=plan.id,
                action=action,
                actor_id=actor.user_id,
                occurred_at=now,
                details=None,
            )
        )

    def create(self, actor: CurrentActor, data: PlanCreate) -> PlanRead:
        with self._uow_factory() as uow:
            self._active_actor(uow, actor)
            target = uow.servers.get(data.server_id)
            if target is None:
                raise NotFound(f"Server {data.server_id} does not exist")
            if not target.enabled:
                raise ServerDisabled(f"Server {target.key} is disabled")

            now = self._clock()
            plan = PlanEntry(
                id=self._plan_id_factory(),
                owner_id=actor.user_id,
                server_id=data.server_id,
                title=data.title,
                project=data.project,
                start_at=data.start_at,
                end_at=data.end_at,
                cpu_cores=data.cpu_cores,
                memory_gb=data.memory_gb,
                gpu_count=data.gpu_count,
                gpu_ids=data.gpu_ids,
                note=data.note,
                cancelled_at=None,
                created_at=now,
                updated_at=now,
            )
            # Advisory only: overlap never blocks publishing an intent.
            existing = uow.plans.list(server_id=plan.server_id, include_cancelled=False)
            capacity = target.capacity or ServerCapacity(None, None, None)
            evaluate_plan_conflicts(plan, existing, capacity)
            uow.plans.add(plan)
            self._audit(uow, actor, "created", plan, now)
            uow.commit()
            return self._read(plan, now)

    def get(self, actor: CurrentActor, plan_id: UUID) -> PlanRead:
        with self._uow_factory() as uow:
            self._active_actor(uow, actor)
            plan = self._plan_or_not_found(uow, plan_id)
            return self._read(plan, self._clock())

    def list(
        self,
        actor: CurrentActor,
        *,
        server_id: UUID | None = None,
        owner_id: UUID | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        include_cancelled: bool = False,
    ) -> builtins.list[PlanRead]:
        with self._uow_factory() as uow:
            self._active_actor(uow, actor)
            now = self._clock()
            plans = uow.plans.list(
                server_id=server_id,
                owner_id=owner_id,
                start=start,
                end=end,
                include_cancelled=include_cancelled,
            )
            return [self._read(plan, now) for plan in plans]

    def update(self, actor: CurrentActor, plan_id: UUID, data: PlanUpdate) -> PlanRead:
        with self._uow_factory() as uow:
            self._active_actor(uow, actor)
            plan = self._plan_or_not_found(uow, plan_id)
            require_self_or_admin(actor, plan.owner_id)

            changes = data.model_dump(exclude_unset=True)
            # Non-nullable plan columns must never be set to null, even though
            # PlanUpdate types them optional for partial-update ergonomics.
            nulled = {field for field in changes if changes[field] is None} & {
                "server_id",
                "title",
                "start_at",
                "end_at",
            }
            if nulled:
                raise DomainValidationError(
                    f"Fields cannot be set to null: {', '.join(sorted(nulled))}"
                )
            if changes.get("server_id") is not None and changes["server_id"] != plan.server_id:
                # Keep update symmetric with create: the target server must exist
                # and be enabled.
                target = uow.servers.get(changes["server_id"])
                if target is None:
                    raise NotFound(f"Server {changes['server_id']} does not exist")
                if not target.enabled:
                    raise ServerDisabled(f"Server {target.key} is disabled")
            merged = replace(plan, **changes, updated_at=self._clock())
            try:
                validate_plan_window(
                    merged.start_at, merged.end_at, merged.gpu_count, merged.gpu_ids
                )
            except ValueError as error:
                raise DomainValidationError(str(error)) from error

            uow.plans.save(merged)
            self._audit(uow, actor, "updated", merged, merged.updated_at)
            uow.commit()
            return self._read(merged, merged.updated_at)

    def cancel(self, actor: CurrentActor, plan_id: UUID) -> PlanRead:
        with self._uow_factory() as uow:
            self._active_actor(uow, actor)
            plan = self._plan_or_not_found(uow, plan_id)
            require_self_or_admin(actor, plan.owner_id)
            now = self._clock()
            if plan.cancelled_at is not None:
                # Idempotent: an already-cancelled plan keeps its first timestamp
                # and does not produce another audit event.
                return self._read(plan, now)

            cancelled = replace(plan, cancelled_at=now, updated_at=now)
            uow.plans.save(cancelled)
            self._audit(uow, actor, "cancelled", cancelled, now)
            uow.commit()
            return self._read(cancelled, now)

    def conflicts(self, actor: CurrentActor, plan_id: UUID) -> builtins.list[PlanConflictRead]:
        with self._uow_factory() as uow:
            self._active_actor(uow, actor)
            plan = self._plan_or_not_found(uow, plan_id)
            server = uow.servers.get(plan.server_id)
            capacity = server.capacity if server is not None else ServerCapacity(None, None, None)
            existing = uow.plans.list(server_id=plan.server_id, include_cancelled=False)
            conflicts = evaluate_plan_conflicts(plan, existing, capacity)
            return [
                PlanConflictRead(
                    resource=conflict.resource,
                    certainty=conflict.certainty,
                    start_at=conflict.start_at,
                    end_at=conflict.end_at,
                    requested=conflict.requested,
                    available=conflict.available,
                    conflicting_plan_ids=conflict.conflicting_plan_ids,
                    reason=conflict.reason,
                )
                for conflict in conflicts
            ]
