from datetime import UTC, datetime, timedelta
from uuid import UUID

from labserver_contracts.common import (
    ConflictCertainty,
    ConflictResource,
    ReservationSource,
    ReservationStatus,
)
from labserver_core.domain.conflicts import evaluate_conflicts
from labserver_core.domain.entities import Reservation, ServerCapacity

SERVER_ID = UUID("00000000-0000-0000-0000-000000000801")
OTHER_SERVER_ID = UUID("00000000-0000-0000-0000-000000000802")
OWNER_ID = UUID("00000000-0000-0000-0000-000000000803")
BASE = datetime(2026, 9, 20, 10, 0, tzinfo=UTC)
NOW = datetime(2026, 9, 15, 7, 0, tzinfo=UTC)


def reservation(
    suffix: int,
    *,
    start_minutes: int,
    end_minutes: int,
    cpu: int = 0,
    memory: float | None = None,
    gpu_count: int = 0,
    gpu_ids: tuple[int, ...] | None = None,
    status: ReservationStatus = ReservationStatus.PLANNED,
    server_id: UUID = SERVER_ID,
) -> Reservation:
    return Reservation(
        id=UUID(f"00000000-0000-0000-0000-{suffix:012d}"),
        request_id=None,
        owner_id=OWNER_ID,
        server_id=server_id,
        title=f"reservation-{suffix}",
        start_at=BASE + timedelta(minutes=start_minutes),
        end_at=BASE + timedelta(minutes=end_minutes),
        cpu_cores=cpu,
        memory_gb=memory,
        gpu_count=gpu_count,
        gpu_ids=gpu_ids,
        status=status,
        source=ReservationSource.ADMIN,
        created_at=NOW,
        updated_at=NOW,
    )


def test_adjacent_half_open_intervals_do_not_conflict() -> None:
    candidate = reservation(
        1,
        start_minutes=0,
        end_minutes=60,
        gpu_count=1,
        gpu_ids=(0,),
    )
    existing = reservation(
        2,
        start_minutes=60,
        end_minutes=120,
        gpu_count=1,
        gpu_ids=(0,),
    )

    conflicts = evaluate_conflicts(candidate, [existing], ServerCapacity(64, 256.0, 4))

    assert conflicts == []


def test_one_minute_explicit_gpu_overlap_is_confirmed() -> None:
    candidate = reservation(
        3,
        start_minutes=0,
        end_minutes=60,
        gpu_count=1,
        gpu_ids=(1,),
    )
    existing = reservation(
        4,
        start_minutes=59,
        end_minutes=120,
        gpu_count=1,
        gpu_ids=(1,),
    )

    conflicts = evaluate_conflicts(candidate, [existing], ServerCapacity(64, 256.0, 4))

    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert conflict.resource is ConflictResource.GPU_DEVICE
    assert conflict.certainty is ConflictCertainty.CONFIRMED
    assert conflict.start_at == BASE + timedelta(minutes=59)
    assert conflict.end_at == BASE + timedelta(minutes=60)
    assert conflict.requested == (1,)
    assert conflict.conflicting_reservation_ids == (existing.id,)


def test_cpu_capacity_conflict_is_limited_to_segment_where_all_overlap() -> None:
    candidate = reservation(5, start_minutes=0, end_minutes=180, cpu=16)
    first = reservation(6, start_minutes=0, end_minutes=120, cpu=12)
    second = reservation(7, start_minutes=60, end_minutes=180, cpu=12)

    conflicts = evaluate_conflicts(
        candidate,
        [first, second],
        ServerCapacity(cpu_cores=32, memory_gb=256.0, gpu_count=4),
    )

    cpu_conflicts = [item for item in conflicts if item.resource is ConflictResource.CPU]
    assert len(cpu_conflicts) == 1
    conflict = cpu_conflicts[0]
    assert conflict.start_at == BASE + timedelta(minutes=60)
    assert conflict.end_at == BASE + timedelta(minutes=120)
    assert conflict.requested == 16.0
    assert conflict.available == 8.0
    assert conflict.conflicting_reservation_ids == (first.id, second.id)


def test_unknown_memory_capacity_does_not_invent_confirmed_conflict() -> None:
    candidate = reservation(8, start_minutes=0, end_minutes=60, memory=256.0)
    existing = reservation(9, start_minutes=0, end_minutes=60, memory=512.0)

    conflicts = evaluate_conflicts(
        candidate,
        [existing],
        ServerCapacity(cpu_cores=64, memory_gb=None, gpu_count=4),
    )

    assert all(item.resource is not ConflictResource.MEMORY for item in conflicts)


def test_explicit_gpu_id_intersection_is_confirmed() -> None:
    candidate = reservation(
        10,
        start_minutes=0,
        end_minutes=60,
        gpu_count=2,
        gpu_ids=(0, 1),
    )
    existing = reservation(
        11,
        start_minutes=0,
        end_minutes=60,
        gpu_count=2,
        gpu_ids=(1, 2),
    )

    conflicts = evaluate_conflicts(candidate, [existing], ServerCapacity(64, 256.0, 4))

    device_conflicts = [
        item for item in conflicts if item.resource is ConflictResource.GPU_DEVICE
    ]
    assert len(device_conflicts) == 1
    assert device_conflicts[0].certainty is ConflictCertainty.CONFIRMED
    assert device_conflicts[0].requested == (1,)
    assert device_conflicts[0].conflicting_reservation_ids == (existing.id,)


def test_disjoint_explicit_gpu_ids_do_not_conflict() -> None:
    candidate = reservation(
        12,
        start_minutes=0,
        end_minutes=60,
        gpu_count=2,
        gpu_ids=(0, 1),
    )
    existing = reservation(
        13,
        start_minutes=0,
        end_minutes=60,
        gpu_count=2,
        gpu_ids=(2, 3),
    )

    conflicts = evaluate_conflicts(candidate, [existing], ServerCapacity(64, 256.0, 4))

    assert conflicts == []


def test_count_only_gpu_requests_within_capacity_do_not_conflict() -> None:
    candidate = reservation(14, start_minutes=0, end_minutes=60, gpu_count=2)
    existing = reservation(15, start_minutes=0, end_minutes=60, gpu_count=2)

    conflicts = evaluate_conflicts(candidate, [existing], ServerCapacity(64, 256.0, 4))

    assert conflicts == []


def test_count_only_gpu_aggregate_over_capacity_is_confirmed() -> None:
    candidate = reservation(16, start_minutes=0, end_minutes=60, gpu_count=2)
    existing = reservation(17, start_minutes=0, end_minutes=60, gpu_count=3)

    conflicts = evaluate_conflicts(candidate, [existing], ServerCapacity(64, 256.0, 4))

    gpu_conflicts = [item for item in conflicts if item.resource is ConflictResource.GPU]
    assert len(gpu_conflicts) == 1
    assert gpu_conflicts[0].certainty is ConflictCertainty.CONFIRMED
    assert gpu_conflicts[0].requested == 2.0
    assert gpu_conflicts[0].available == 1.0
    assert gpu_conflicts[0].conflicting_reservation_ids == (existing.id,)


def test_explicit_candidate_vs_count_only_existing_is_uncertain_even_when_aggregate_fits() -> None:
    candidate = reservation(
        18,
        start_minutes=0,
        end_minutes=60,
        gpu_count=1,
        gpu_ids=(0,),
    )
    existing = reservation(19, start_minutes=0, end_minutes=60, gpu_count=2)

    conflicts = evaluate_conflicts(candidate, [existing], ServerCapacity(64, 256.0, 4))

    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert conflict.resource is ConflictResource.GPU_DEVICE
    assert conflict.certainty is ConflictCertainty.UNCERTAIN
    assert conflict.requested == (0,)
    assert conflict.available is None
    assert conflict.conflicting_reservation_ids == (existing.id,)


def test_uncertain_device_warning_can_coexist_with_confirmed_aggregate_gpu_conflict() -> None:
    candidate = reservation(
        20,
        start_minutes=0,
        end_minutes=60,
        gpu_count=2,
        gpu_ids=(0, 1),
    )
    existing = reservation(21, start_minutes=0, end_minutes=60, gpu_count=3)

    conflicts = evaluate_conflicts(candidate, [existing], ServerCapacity(64, 256.0, 4))

    assert {(item.resource, item.certainty) for item in conflicts} == {
        (ConflictResource.GPU, ConflictCertainty.CONFIRMED),
        (ConflictResource.GPU_DEVICE, ConflictCertainty.UNCERTAIN),
    }


def test_cancelled_reservations_do_not_consume_capacity() -> None:
    candidate = reservation(22, start_minutes=0, end_minutes=60, cpu=32, gpu_count=2)
    cancelled = reservation(
        23,
        start_minutes=0,
        end_minutes=60,
        cpu=64,
        gpu_count=4,
        status=ReservationStatus.CANCELLED,
    )

    conflicts = evaluate_conflicts(candidate, [cancelled], ServerCapacity(64, 256.0, 4))

    assert conflicts == []


def test_different_server_reservations_are_ignored() -> None:
    candidate = reservation(24, start_minutes=0, end_minutes=60, cpu=64)
    other_server = reservation(
        25,
        start_minutes=0,
        end_minutes=60,
        cpu=64,
        server_id=OTHER_SERVER_ID,
    )

    conflicts = evaluate_conflicts(candidate, [other_server], ServerCapacity(64, 256.0, 4))

    assert conflicts == []


def test_adjacent_identical_conflict_segments_are_coalesced() -> None:
    candidate = reservation(26, start_minutes=0, end_minutes=120, cpu=20)
    existing = reservation(27, start_minutes=0, end_minutes=120, cpu=20)
    boundary_only = reservation(28, start_minutes=60, end_minutes=60, cpu=1)

    conflicts = evaluate_conflicts(
        candidate,
        [existing, boundary_only],
        ServerCapacity(cpu_cores=32, memory_gb=256.0, gpu_count=4),
    )

    cpu_conflicts = [item for item in conflicts if item.resource is ConflictResource.CPU]
    assert len(cpu_conflicts) == 1
    assert cpu_conflicts[0].start_at == BASE
    assert cpu_conflicts[0].end_at == BASE + timedelta(minutes=120)
