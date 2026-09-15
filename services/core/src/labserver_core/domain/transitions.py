from dataclasses import replace

from labserver_contracts.common import TaskRequestStatus, UserRole

from .entities import ManagedServer, TaskRequest
from .errors import (
    CapacityExceeded,
    DomainValidationError,
    Forbidden,
    InvalidTransition,
    ServerDisabled,
)

_ALLOWED_TRANSITIONS: dict[TaskRequestStatus, frozenset[TaskRequestStatus]] = {
    TaskRequestStatus.DRAFT: frozenset(
        {TaskRequestStatus.SUBMITTED, TaskRequestStatus.CANCELLED}
    ),
    TaskRequestStatus.SUBMITTED: frozenset(
        {
            TaskRequestStatus.APPROVED,
            TaskRequestStatus.REJECTED,
            TaskRequestStatus.CANCELLED,
        }
    ),
    TaskRequestStatus.APPROVED: frozenset(),
    TaskRequestStatus.REJECTED: frozenset(),
    TaskRequestStatus.CANCELLED: frozenset(),
}

_ADMIN_ONLY_TARGETS = frozenset({TaskRequestStatus.APPROVED, TaskRequestStatus.REJECTED})


def _validate_submission_capacity(request: TaskRequest, server: ManagedServer) -> None:
    capacity = server.capacity

    if capacity.cpu_cores is not None and request.requested_cpu_cores > capacity.cpu_cores:
        raise CapacityExceeded("cpu", request.requested_cpu_cores, capacity.cpu_cores)

    if (
        capacity.memory_gb is not None
        and request.requested_memory_gb is not None
        and request.requested_memory_gb > capacity.memory_gb
    ):
        raise CapacityExceeded("memory", request.requested_memory_gb, capacity.memory_gb)

    if capacity.gpu_count is not None:
        if request.requested_gpu_count > capacity.gpu_count:
            raise CapacityExceeded("gpu", request.requested_gpu_count, capacity.gpu_count)
        if request.preferred_gpu_ids is not None:
            invalid_ids = [
                gpu_id
                for gpu_id in request.preferred_gpu_ids
                if gpu_id >= capacity.gpu_count
            ]
            if invalid_ids:
                raise CapacityExceeded("gpu_device", max(invalid_ids) + 1, capacity.gpu_count)


def transition_request(
    request: TaskRequest,
    target: TaskRequestStatus,
    actor_role: UserRole,
    *,
    server: ManagedServer,
    allow_capacity_override: bool = False,
) -> TaskRequest:
    if target in _ADMIN_ONLY_TARGETS and actor_role is not UserRole.ADMIN:
        raise Forbidden(f"Only an admin can transition a request to {target.value}")

    if allow_capacity_override and actor_role is not UserRole.ADMIN:
        raise Forbidden("Only an admin can override server capacity")

    if target not in _ALLOWED_TRANSITIONS[request.status]:
        raise InvalidTransition(request.status, target)

    if target is TaskRequestStatus.SUBMITTED:
        if server.id != request.preferred_server_id:
            raise DomainValidationError("Request preferred server does not match supplied server")
        if not server.enabled:
            raise ServerDisabled(f"Server {server.key} is disabled")
        if not allow_capacity_override:
            _validate_submission_capacity(request, server)

    return replace(request, status=target)
