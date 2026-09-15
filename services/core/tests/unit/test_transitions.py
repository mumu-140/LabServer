from datetime import UTC, datetime
from uuid import UUID

import pytest
from labserver_contracts.common import TaskRequestStatus, UserRole
from labserver_core.domain.entities import ManagedServer, ServerCapacity, TaskRequest
from labserver_core.domain.errors import (
    CapacityExceeded,
    Forbidden,
    InvalidTransition,
    ServerDisabled,
)
from labserver_core.domain.transitions import transition_request

REQUEST_ID = UUID("00000000-0000-0000-0000-000000000101")
USER_ID = UUID("00000000-0000-0000-0000-000000000201")
SERVER_ID = UUID("00000000-0000-0000-0000-000000000301")
NOW = datetime(2026, 9, 15, 5, 0, tzinfo=UTC)
START = datetime(2026, 9, 18, 0, 0, tzinfo=UTC)


def make_server(
    *,
    enabled: bool = True,
    cpu_cores: int | None = 64,
    memory_gb: float | None = 256.0,
    gpu_count: int | None = 4,
) -> ManagedServer:
    return ManagedServer(
        id=SERVER_ID,
        key="fwq10",
        display_name="fwq10",
        enabled=enabled,
        capacity=ServerCapacity(
            cpu_cores=cpu_cores,
            memory_gb=memory_gb,
            gpu_count=gpu_count,
        ),
        created_at=NOW,
        updated_at=NOW,
    )


def make_request(
    *,
    status: TaskRequestStatus = TaskRequestStatus.DRAFT,
    cpu_cores: int = 32,
    memory_gb: float | None = 128.0,
    gpu_count: int = 2,
    gpu_ids: tuple[int, ...] | None = (0, 1),
) -> TaskRequest:
    return TaskRequest(
        id=REQUEST_ID,
        requester_id=USER_ID,
        title="Poplar assembly",
        project="Populus",
        preferred_server_id=SERVER_ID,
        planned_start=START,
        planned_duration_minutes=2880,
        requested_cpu_cores=cpu_cores,
        requested_memory_gb=memory_gb,
        requested_gpu_count=gpu_count,
        preferred_gpu_ids=gpu_ids,
        note="HiFi assembly",
        status=status,
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.mark.parametrize(
    ("source", "target", "role"),
    [
        (TaskRequestStatus.DRAFT, TaskRequestStatus.SUBMITTED, UserRole.MEMBER),
        (TaskRequestStatus.SUBMITTED, TaskRequestStatus.APPROVED, UserRole.ADMIN),
        (TaskRequestStatus.SUBMITTED, TaskRequestStatus.REJECTED, UserRole.ADMIN),
        (TaskRequestStatus.DRAFT, TaskRequestStatus.CANCELLED, UserRole.MEMBER),
        (TaskRequestStatus.SUBMITTED, TaskRequestStatus.CANCELLED, UserRole.MEMBER),
    ],
)
def test_allowed_request_transitions(
    source: TaskRequestStatus,
    target: TaskRequestStatus,
    role: UserRole,
) -> None:
    request = make_request(status=source)

    result = transition_request(request, target, role, server=make_server())

    assert result.status is target
    assert result.id == request.id
    assert result.title == request.title
    assert request.status is source


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (TaskRequestStatus.APPROVED, TaskRequestStatus.SUBMITTED),
        (TaskRequestStatus.REJECTED, TaskRequestStatus.APPROVED),
        (TaskRequestStatus.CANCELLED, TaskRequestStatus.SUBMITTED),
    ],
)
def test_invalid_request_transitions_are_rejected(
    source: TaskRequestStatus,
    target: TaskRequestStatus,
) -> None:
    with pytest.raises(InvalidTransition) as exc_info:
        transition_request(
            make_request(status=source), target, UserRole.ADMIN, server=make_server()
        )

    assert exc_info.value.code == "invalid_transition"


@pytest.mark.parametrize("target", [TaskRequestStatus.APPROVED, TaskRequestStatus.REJECTED])
def test_member_cannot_approve_or_reject(target: TaskRequestStatus) -> None:
    with pytest.raises(Forbidden) as exc_info:
        transition_request(
            make_request(status=TaskRequestStatus.SUBMITTED),
            target,
            UserRole.MEMBER,
            server=make_server(),
        )

    assert exc_info.value.code == "forbidden"


def test_submit_rejects_disabled_server() -> None:
    with pytest.raises(ServerDisabled) as exc_info:
        transition_request(
            make_request(),
            TaskRequestStatus.SUBMITTED,
            UserRole.MEMBER,
            server=make_server(enabled=False),
        )

    assert exc_info.value.code == "server_disabled"


@pytest.mark.parametrize(
    ("task_request", "expected_resource"),
    [
        (make_request(cpu_cores=65), "cpu"),
        (make_request(memory_gb=257.0), "memory"),
        (make_request(gpu_count=5, gpu_ids=None), "gpu"),
        (make_request(gpu_count=1, gpu_ids=(4,)), "gpu_device"),
    ],
)
def test_submit_rejects_known_capacity_excess(
    task_request: TaskRequest,
    expected_resource: str,
) -> None:
    with pytest.raises(CapacityExceeded) as exc_info:
        transition_request(
            task_request,
            TaskRequestStatus.SUBMITTED,
            UserRole.MEMBER,
            server=make_server(),
        )

    assert exc_info.value.code == "capacity_exceeded"
    assert exc_info.value.resource == expected_resource


def test_unknown_capacity_does_not_invent_a_limit() -> None:
    result = transition_request(
        make_request(cpu_cores=512, memory_gb=4096.0, gpu_count=16, gpu_ids=None),
        TaskRequestStatus.SUBMITTED,
        UserRole.MEMBER,
        server=make_server(cpu_cores=None, memory_gb=None, gpu_count=None),
    )

    assert result.status is TaskRequestStatus.SUBMITTED


def test_admin_can_explicitly_override_known_capacity() -> None:
    result = transition_request(
        make_request(cpu_cores=128, memory_gb=512.0, gpu_count=8, gpu_ids=None),
        TaskRequestStatus.SUBMITTED,
        UserRole.ADMIN,
        server=make_server(),
        allow_capacity_override=True,
    )

    assert result.status is TaskRequestStatus.SUBMITTED


def test_member_cannot_use_capacity_override_flag() -> None:
    with pytest.raises(Forbidden) as exc_info:
        transition_request(
            make_request(cpu_cores=128),
            TaskRequestStatus.SUBMITTED,
            UserRole.MEMBER,
            server=make_server(),
            allow_capacity_override=True,
        )

    assert exc_info.value.code == "forbidden"
