from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from labserver_contracts.common import (
    ConflictCertainty,
    ConflictResource,
)
from labserver_contracts.plans import PlanDisplayState

from .entities import PlanEntry, ServerCapacity

NumericOrDevices = float | tuple[int, ...]


@dataclass(frozen=True, slots=True)
class Conflict:
    resource: ConflictResource
    certainty: ConflictCertainty
    start_at: datetime
    end_at: datetime
    requested: NumericOrDevices
    available: NumericOrDevices | None
    conflicting_plan_ids: tuple[UUID, ...]
    reason: str


def plan_display_state(plan: PlanEntry, now: datetime) -> PlanDisplayState:
    """Display state is derived from time only; it is never persisted."""
    if plan.cancelled_at is not None:
        return PlanDisplayState.CANCELLED
    if now < plan.start_at:
        return PlanDisplayState.UPCOMING
    if now < plan.end_at:
        return PlanDisplayState.ONGOING
    return PlanDisplayState.PAST


def _overlaps(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> bool:
    return start_a < end_b and end_a > start_b


def _active_for_segment(plan: PlanEntry, start_at: datetime, end_at: datetime) -> bool:
    return plan.start_at < end_at and plan.end_at > start_at


def _ids(plans: Sequence[PlanEntry]) -> tuple[UUID, ...]:
    return tuple(sorted((plan.id for plan in plans), key=str))


def _capacity_conflict(
    *,
    resource: ConflictResource,
    start_at: datetime,
    end_at: datetime,
    candidate_requested: float,
    existing_requested: float,
    capacity: float | None,
    conflicting: Sequence[PlanEntry],
) -> Conflict | None:
    if capacity is None or candidate_requested <= 0:
        return None
    if candidate_requested + existing_requested <= capacity:
        return None

    available = max(0.0, capacity - existing_requested)
    return Conflict(
        resource=resource,
        certainty=ConflictCertainty.CONFIRMED,
        start_at=start_at,
        end_at=end_at,
        requested=candidate_requested,
        available=available,
        conflicting_plan_ids=_ids(conflicting),
        reason=(
            f"Requested {resource.value} capacity {candidate_requested:g} exceeds "
            f"the {available:g} available during this interval"
        ),
    )


def _declared_gpu_count(plan: PlanEntry) -> int:
    """Undeclared GPU intent is *not declared*, never 0 usage of a known amount."""
    if plan.gpu_ids is not None:
        return len(plan.gpu_ids)
    return plan.gpu_count or 0


def _device_conflicts(
    candidate: PlanEntry,
    active: Sequence[PlanEntry],
    start_at: datetime,
    end_at: datetime,
) -> list[Conflict]:
    if not candidate.gpu_ids:
        return []

    candidate_ids = set(candidate.gpu_ids)
    confirmed_plans: list[PlanEntry] = []
    confirmed_devices: set[int] = set()
    uncertain_plans: list[PlanEntry] = []

    for plan in active:
        if _declared_gpu_count(plan) <= 0:
            continue
        if plan.gpu_ids is None:
            uncertain_plans.append(plan)
            continue

        overlap = candidate_ids.intersection(plan.gpu_ids)
        if overlap:
            confirmed_plans.append(plan)
            confirmed_devices.update(overlap)

    conflicts: list[Conflict] = []
    if confirmed_devices:
        devices = tuple(sorted(confirmed_devices))
        conflicts.append(
            Conflict(
                resource=ConflictResource.GPU_DEVICE,
                certainty=ConflictCertainty.CONFIRMED,
                start_at=start_at,
                end_at=end_at,
                requested=devices,
                available=(),
                conflicting_plan_ids=_ids(confirmed_plans),
                reason=(
                    "Explicit GPU device plan overlaps on device(s): "
                    + ", ".join(str(device) for device in devices)
                ),
            )
        )

    if uncertain_plans:
        conflicts.append(
            Conflict(
                resource=ConflictResource.GPU_DEVICE,
                certainty=ConflictCertainty.UNCERTAIN,
                start_at=start_at,
                end_at=end_at,
                requested=tuple(sorted(candidate_ids)),
                available=None,
                conflicting_plan_ids=_ids(uncertain_plans),
                reason=(
                    "Candidate declares explicit GPU device(s), but overlapping plan(s) "
                    "do not declare device IDs"
                ),
            )
        )

    return conflicts


def _same_conflict_shape(left: Conflict, right: Conflict) -> bool:
    return (
        left.resource is right.resource
        and left.certainty is right.certainty
        and left.requested == right.requested
        and left.available == right.available
        and left.conflicting_plan_ids == right.conflicting_plan_ids
        and left.reason == right.reason
        and left.end_at == right.start_at
    )


def _coalesce(conflicts: Sequence[Conflict]) -> list[Conflict]:
    if not conflicts:
        return []

    ordered = sorted(
        conflicts,
        key=lambda item: (
            item.start_at,
            item.end_at,
            item.resource.value,
            item.certainty.value,
            tuple(str(value) for value in item.conflicting_plan_ids),
        ),
    )
    merged: list[Conflict] = []
    for conflict in ordered:
        match_index = next(
            (
                index
                for index in range(len(merged) - 1, -1, -1)
                if _same_conflict_shape(merged[index], conflict)
            ),
            None,
        )
        if match_index is not None:
            merged[match_index] = replace(merged[match_index], end_at=conflict.end_at)
        else:
            merged.append(conflict)
    return sorted(
        merged,
        key=lambda item: (item.start_at, item.resource.value, item.certainty.value),
    )


def _invalid_candidate_gpu_devices(
    candidate: PlanEntry,
    capacity: ServerCapacity,
) -> Conflict | None:
    if candidate.gpu_ids is None or capacity.gpu_count is None:
        return None

    valid = tuple(range(capacity.gpu_count))
    invalid = tuple(sorted(device for device in candidate.gpu_ids if device >= capacity.gpu_count))
    if not invalid:
        return None

    return Conflict(
        resource=ConflictResource.GPU_DEVICE,
        certainty=ConflictCertainty.CONFIRMED,
        start_at=candidate.start_at,
        end_at=candidate.end_at,
        requested=invalid,
        available=valid,
        conflicting_plan_ids=(),
        reason="Explicit GPU device plan references device(s) outside declared server capacity",
    )


def evaluate_plan_conflicts(
    candidate: PlanEntry,
    existing: Sequence[PlanEntry],
    capacity: ServerCapacity,
) -> tuple[Conflict, ...]:
    """Advisory overlap evaluation. Never blocks creating or updating a plan."""
    if candidate.cancelled_at is not None or candidate.start_at >= candidate.end_at:
        return ()

    relevant = [
        plan
        for plan in existing
        if plan.id != candidate.id
        and plan.server_id == candidate.server_id
        and plan.cancelled_at is None
        and plan.start_at < plan.end_at
        and _overlaps(candidate.start_at, candidate.end_at, plan.start_at, plan.end_at)
    ]

    # Standalone overcommit is still advisory: evaluate the candidate interval
    # even when no existing plan overlaps, with zero existing usage.
    boundaries = {candidate.start_at, candidate.end_at}
    for plan in relevant:
        boundaries.add(max(candidate.start_at, plan.start_at))
        boundaries.add(min(candidate.end_at, plan.end_at))
    ordered_boundaries = sorted(boundaries)

    conflicts: list[Conflict] = []
    for start_at, end_at in zip(ordered_boundaries, ordered_boundaries[1:], strict=False):
        if start_at >= end_at:
            continue
        active = [plan for plan in relevant if _active_for_segment(plan, start_at, end_at)]

        cpu_consumers = [
            plan for plan in active if plan.cpu_cores is not None and plan.cpu_cores > 0
        ]
        cpu_conflict = _capacity_conflict(
            resource=ConflictResource.CPU,
            start_at=start_at,
            end_at=end_at,
            candidate_requested=float(candidate.cpu_cores or 0),
            existing_requested=float(sum(plan.cpu_cores or 0 for plan in cpu_consumers)),
            capacity=float(capacity.cpu_cores) if capacity.cpu_cores is not None else None,
            conflicting=cpu_consumers,
        )
        if cpu_conflict is not None:
            conflicts.append(cpu_conflict)

        memory_consumers = [
            plan for plan in active if plan.memory_gb is not None and plan.memory_gb > 0
        ]
        memory_conflict = _capacity_conflict(
            resource=ConflictResource.MEMORY,
            start_at=start_at,
            end_at=end_at,
            candidate_requested=float(candidate.memory_gb or 0.0),
            existing_requested=float(sum(plan.memory_gb or 0.0 for plan in memory_consumers)),
            capacity=float(capacity.memory_gb) if capacity.memory_gb is not None else None,
            conflicting=memory_consumers,
        )
        if memory_conflict is not None:
            conflicts.append(memory_conflict)

        gpu_consumers = [plan for plan in active if _declared_gpu_count(plan) > 0]
        gpu_conflict = _capacity_conflict(
            resource=ConflictResource.GPU,
            start_at=start_at,
            end_at=end_at,
            candidate_requested=float(_declared_gpu_count(candidate)),
            existing_requested=float(sum(_declared_gpu_count(plan) for plan in gpu_consumers)),
            capacity=float(capacity.gpu_count) if capacity.gpu_count is not None else None,
            conflicting=gpu_consumers,
        )
        if gpu_conflict is not None:
            conflicts.append(gpu_conflict)

        conflicts.extend(_device_conflicts(candidate, active, start_at, end_at))

    invalid_devices = _invalid_candidate_gpu_devices(candidate, capacity)
    if invalid_devices is not None:
        conflicts.append(invalid_devices)

    return tuple(_coalesce(conflicts))
