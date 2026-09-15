from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from labserver_contracts.common import ConflictCertainty, ConflictResource
from labserver_contracts.plans import PlanDisplayState
from labserver_core.domain.conflicts import evaluate_plan_conflicts
from labserver_core.domain.entities import PlanEntry, ServerCapacity, plan_display_state

SERVER_A = UUID("00000000-0000-0000-0000-0000000000a1")
SERVER_B = UUID("00000000-0000-0000-0000-0000000000b2")
OWNER = UUID("00000000-0000-0000-0000-0000000000c3")


def dt(hour: int) -> datetime:
    return datetime(2026, 9, 18, hour, tzinfo=UTC)


def capacity(
    *,
    cpu_cores: int | None = 64,
    memory_gb: float | None = 256.0,
    gpu_count: int | None = 4,
) -> ServerCapacity:
    return ServerCapacity(cpu_cores=cpu_cores, memory_gb=memory_gb, gpu_count=gpu_count)


def plan(
    *,
    start_at: datetime,
    end_at: datetime,
    server_id: UUID = SERVER_A,
    cpu_cores: int | None = None,
    memory_gb: float | None = None,
    gpu_count: int | None = None,
    gpu_ids: tuple[int, ...] | None = None,
    cancelled_at: datetime | None = None,
    plan_id: UUID | None = None,
) -> PlanEntry:
    now = dt(0)
    return PlanEntry(
        id=plan_id or uuid4(),
        owner_id=OWNER,
        server_id=server_id,
        title="Poplar assembly",
        project=None,
        start_at=start_at,
        end_at=end_at,
        cpu_cores=cpu_cores,
        memory_gb=memory_gb,
        gpu_count=gpu_count,
        gpu_ids=gpu_ids,
        note=None,
        cancelled_at=cancelled_at,
        created_at=now,
        updated_at=now,
    )


def resources(conflicts: Sequence[object]) -> set[ConflictResource]:
    return {conflict.resource for conflict in conflicts}  # type: ignore[attr-defined]


def test_adjacent_plans_do_not_overlap() -> None:
    first = plan(start_at=dt(10), end_at=dt(12), gpu_ids=(0,), gpu_count=1)
    second = plan(start_at=dt(12), end_at=dt(14), gpu_ids=(0,), gpu_count=1)

    assert evaluate_plan_conflicts(second, [first], capacity()) == ()


def test_explicit_same_gpu_overlap_warns() -> None:
    first = plan(start_at=dt(10), end_at=dt(13), gpu_ids=(0,), gpu_count=1)
    second = plan(start_at=dt(12), end_at=dt(14), gpu_ids=(0,), gpu_count=1)

    conflicts = evaluate_plan_conflicts(second, [first], capacity())

    assert resources(conflicts) == {ConflictResource.GPU_DEVICE}
    assert conflicts[0].certainty is ConflictCertainty.CONFIRMED
    assert conflicts[0].requested == (0,)
    assert conflicts[0].conflicting_plan_ids == (first.id,)


def test_explicit_distinct_gpu_ids_do_not_conflict() -> None:
    first = plan(start_at=dt(10), end_at=dt(14), gpu_ids=(0, 1), gpu_count=2)
    second = plan(start_at=dt(10), end_at=dt(14), gpu_ids=(2, 3), gpu_count=2)

    assert evaluate_plan_conflicts(second, [first], capacity()) == ()


def test_aggregate_gpu_count_oversubscription_warns() -> None:
    first = plan(start_at=dt(10), end_at=dt(14), gpu_count=3)
    second = plan(start_at=dt(11), end_at=dt(13), gpu_count=2)

    conflicts = evaluate_plan_conflicts(second, [first], capacity(gpu_count=4))

    assert resources(conflicts) == {ConflictResource.GPU}
    assert conflicts[0].certainty is ConflictCertainty.CONFIRMED
    assert conflicts[0].requested == 2.0
    assert conflicts[0].available == 1.0


def test_aggregate_gpu_within_capacity_does_not_warn() -> None:
    first = plan(start_at=dt(10), end_at=dt(14), gpu_count=2)
    second = plan(start_at=dt(11), end_at=dt(13), gpu_count=2)

    assert evaluate_plan_conflicts(second, [first], capacity(gpu_count=4)) == ()


def test_mixed_explicit_and_count_only_is_uncertain() -> None:
    count_only = plan(start_at=dt(10), end_at=dt(14), gpu_count=1)
    explicit = plan(start_at=dt(11), end_at=dt(13), gpu_ids=(0,), gpu_count=1)

    conflicts = evaluate_plan_conflicts(explicit, [count_only], capacity())

    device_conflicts = [
        conflict for conflict in conflicts if conflict.resource is ConflictResource.GPU_DEVICE
    ]
    assert len(device_conflicts) == 1
    assert device_conflicts[0].certainty is ConflictCertainty.UNCERTAIN
    assert device_conflicts[0].available is None
    assert device_conflicts[0].conflicting_plan_ids == (count_only.id,)


def test_cpu_oversubscription_warns() -> None:
    first = plan(start_at=dt(10), end_at=dt(14), cpu_cores=48)
    second = plan(start_at=dt(11), end_at=dt(13), cpu_cores=32)

    conflicts = evaluate_plan_conflicts(second, [first], capacity(cpu_cores=64))

    assert resources(conflicts) == {ConflictResource.CPU}
    assert conflicts[0].requested == 32.0
    assert conflicts[0].available == 16.0


def test_memory_oversubscription_warns() -> None:
    first = plan(start_at=dt(10), end_at=dt(14), memory_gb=200.0)
    second = plan(start_at=dt(11), end_at=dt(13), memory_gb=100.0)

    conflicts = evaluate_plan_conflicts(second, [first], capacity(memory_gb=256.0))

    assert resources(conflicts) == {ConflictResource.MEMORY}
    assert conflicts[0].requested == 100.0
    assert conflicts[0].available == 56.0


def test_undeclared_resources_are_not_counted_as_zero_usage() -> None:
    undeclared = plan(start_at=dt(10), end_at=dt(14))
    candidate = plan(start_at=dt(11), end_at=dt(13), cpu_cores=64, memory_gb=256.0, gpu_count=4)

    assert evaluate_plan_conflicts(candidate, [undeclared], capacity()) == ()


def test_candidate_without_declared_resources_never_conflicts() -> None:
    heavy = plan(start_at=dt(10), end_at=dt(14), cpu_cores=64, memory_gb=256.0, gpu_count=4)
    candidate = plan(start_at=dt(11), end_at=dt(13))

    assert evaluate_plan_conflicts(candidate, [heavy], capacity()) == ()


def test_cancelled_existing_plans_are_ignored() -> None:
    cancelled = plan(
        start_at=dt(10),
        end_at=dt(14),
        gpu_ids=(0,),
        gpu_count=1,
        cancelled_at=dt(9),
    )
    candidate = plan(start_at=dt(11), end_at=dt(13), gpu_ids=(0,), gpu_count=1)

    assert evaluate_plan_conflicts(candidate, [cancelled], capacity()) == ()


def test_cancelled_candidate_has_no_conflicts() -> None:
    existing = plan(start_at=dt(10), end_at=dt(14), gpu_ids=(0,), gpu_count=1)
    candidate = plan(
        start_at=dt(11),
        end_at=dt(13),
        gpu_ids=(0,),
        gpu_count=1,
        cancelled_at=dt(12),
    )

    assert evaluate_plan_conflicts(candidate, [existing], capacity()) == ()


def test_plans_on_other_servers_are_ignored() -> None:
    other_server = plan(
        start_at=dt(10), end_at=dt(14), server_id=SERVER_B, gpu_ids=(0,), gpu_count=1
    )
    candidate = plan(start_at=dt(11), end_at=dt(13), gpu_ids=(0,), gpu_count=1)

    assert evaluate_plan_conflicts(candidate, [other_server], capacity()) == ()


def test_plan_excludes_itself_from_conflicts() -> None:
    plan_id = uuid4()
    existing = plan(start_at=dt(10), end_at=dt(14), gpu_ids=(0,), gpu_count=1, plan_id=plan_id)
    candidate = plan(start_at=dt(10), end_at=dt(14), gpu_ids=(0,), gpu_count=1, plan_id=plan_id)

    assert evaluate_plan_conflicts(candidate, [existing], capacity()) == ()


def test_unknown_capacity_skips_aggregate_checks() -> None:
    first = plan(start_at=dt(10), end_at=dt(14), gpu_count=3)
    second = plan(start_at=dt(11), end_at=dt(13), gpu_count=3)

    conflicts = evaluate_plan_conflicts(
        second, [first], capacity(cpu_cores=None, memory_gb=None, gpu_count=None)
    )

    assert conflicts == ()


def test_display_state_is_derived_from_time() -> None:
    entry = plan(start_at=dt(10), end_at=dt(12))

    assert plan_display_state(entry, dt(9)) is PlanDisplayState.UPCOMING
    assert plan_display_state(entry, dt(10)) is PlanDisplayState.ONGOING
    assert plan_display_state(entry, dt(11)) is PlanDisplayState.ONGOING
    assert plan_display_state(entry, dt(12)) is PlanDisplayState.PAST
    assert plan_display_state(entry, dt(13)) is PlanDisplayState.PAST


def test_display_state_cancelled_wins_over_time() -> None:
    entry = plan(start_at=dt(10), end_at=dt(12), cancelled_at=dt(9))

    assert plan_display_state(entry, dt(11)) is PlanDisplayState.CANCELLED
    assert plan_display_state(entry, dt(13)) is PlanDisplayState.CANCELLED
