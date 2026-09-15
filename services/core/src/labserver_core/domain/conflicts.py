from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from labserver_contracts.common import (
    ConflictCertainty,
    ConflictResource,
    ReservationStatus,
)

from .entities import Reservation, ServerCapacity

NumericOrDevices = float | tuple[int, ...]


@dataclass(frozen=True, slots=True)
class Conflict:
    resource: ConflictResource
    certainty: ConflictCertainty
    start_at: datetime
    end_at: datetime
    requested: NumericOrDevices
    available: NumericOrDevices | None
    conflicting_reservation_ids: tuple[UUID, ...]
    reason: str


def _overlaps(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> bool:
    return start_a < end_b and end_a > start_b


def _active_for_segment(
    reservation: Reservation,
    start_at: datetime,
    end_at: datetime,
) -> bool:
    return reservation.start_at < end_at and reservation.end_at > start_at


def _ids(reservations: Sequence[Reservation]) -> tuple[UUID, ...]:
    return tuple(sorted((reservation.id for reservation in reservations), key=str))


def _capacity_conflict(
    *,
    resource: ConflictResource,
    start_at: datetime,
    end_at: datetime,
    candidate_requested: float,
    existing_requested: float,
    capacity: float | None,
    conflicting: Sequence[Reservation],
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
        conflicting_reservation_ids=_ids(conflicting),
        reason=(
            f"Requested {resource.value} capacity {candidate_requested:g} exceeds "
            f"the {available:g} available during this interval"
        ),
    )


def _device_conflicts(
    candidate: Reservation,
    active: Sequence[Reservation],
    start_at: datetime,
    end_at: datetime,
) -> list[Conflict]:
    if not candidate.gpu_ids:
        return []

    candidate_ids = set(candidate.gpu_ids)
    confirmed_reservations: list[Reservation] = []
    confirmed_devices: set[int] = set()
    uncertain_reservations: list[Reservation] = []

    for reservation in active:
        if reservation.gpu_count <= 0:
            continue
        if reservation.gpu_ids is None:
            uncertain_reservations.append(reservation)
            continue

        overlap = candidate_ids.intersection(reservation.gpu_ids)
        if overlap:
            confirmed_reservations.append(reservation)
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
                conflicting_reservation_ids=_ids(confirmed_reservations),
                reason=(
                    "Explicit GPU device reservation overlaps on device(s): "
                    + ", ".join(str(device) for device in devices)
                ),
            )
        )

    if uncertain_reservations:
        conflicts.append(
            Conflict(
                resource=ConflictResource.GPU_DEVICE,
                certainty=ConflictCertainty.UNCERTAIN,
                start_at=start_at,
                end_at=end_at,
                requested=tuple(sorted(candidate_ids)),
                available=None,
                conflicting_reservation_ids=_ids(uncertain_reservations),
                reason=(
                    "Candidate requests explicit GPU device(s), but overlapping reservation(s) "
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
        and left.conflicting_reservation_ids == right.conflicting_reservation_ids
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
            tuple(str(value) for value in item.conflicting_reservation_ids),
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


def evaluate_conflicts(
    candidate: Reservation,
    existing: Sequence[Reservation],
    capacity: ServerCapacity,
) -> list[Conflict]:
    if candidate.status is ReservationStatus.CANCELLED or candidate.start_at >= candidate.end_at:
        return []

    relevant = [
        reservation
        for reservation in existing
        if reservation.id != candidate.id
        and reservation.server_id == candidate.server_id
        and reservation.status is not ReservationStatus.CANCELLED
        and reservation.start_at < reservation.end_at
        and _overlaps(
            candidate.start_at,
            candidate.end_at,
            reservation.start_at,
            reservation.end_at,
        )
    ]
    if not relevant:
        return []

    boundaries = {candidate.start_at, candidate.end_at}
    for reservation in relevant:
        boundaries.add(max(candidate.start_at, reservation.start_at))
        boundaries.add(min(candidate.end_at, reservation.end_at))
    ordered_boundaries = sorted(boundaries)

    conflicts: list[Conflict] = []
    for start_at, end_at in zip(ordered_boundaries, ordered_boundaries[1:], strict=False):
        if start_at >= end_at:
            continue
        active = [
            reservation
            for reservation in relevant
            if _active_for_segment(reservation, start_at, end_at)
        ]
        if not active:
            continue

        cpu_consumers = [reservation for reservation in active if reservation.cpu_cores > 0]
        cpu_conflict = _capacity_conflict(
            resource=ConflictResource.CPU,
            start_at=start_at,
            end_at=end_at,
            candidate_requested=float(candidate.cpu_cores),
            existing_requested=float(sum(item.cpu_cores for item in cpu_consumers)),
            capacity=float(capacity.cpu_cores) if capacity.cpu_cores is not None else None,
            conflicting=cpu_consumers,
        )
        if cpu_conflict is not None:
            conflicts.append(cpu_conflict)

        memory_consumers = [
            reservation
            for reservation in active
            if reservation.memory_gb is not None and reservation.memory_gb > 0
        ]
        memory_conflict = _capacity_conflict(
            resource=ConflictResource.MEMORY,
            start_at=start_at,
            end_at=end_at,
            candidate_requested=float(candidate.memory_gb or 0.0),
            existing_requested=float(sum(item.memory_gb or 0.0 for item in memory_consumers)),
            capacity=float(capacity.memory_gb) if capacity.memory_gb is not None else None,
            conflicting=memory_consumers,
        )
        if memory_conflict is not None:
            conflicts.append(memory_conflict)

        gpu_consumers = [reservation for reservation in active if reservation.gpu_count > 0]
        gpu_conflict = _capacity_conflict(
            resource=ConflictResource.GPU,
            start_at=start_at,
            end_at=end_at,
            candidate_requested=float(candidate.gpu_count),
            existing_requested=float(sum(item.gpu_count for item in gpu_consumers)),
            capacity=float(capacity.gpu_count) if capacity.gpu_count is not None else None,
            conflicting=gpu_consumers,
        )
        if gpu_conflict is not None:
            conflicts.append(gpu_conflict)

        conflicts.extend(_device_conflicts(candidate, active, start_at, end_at))

    return _coalesce(conflicts)
