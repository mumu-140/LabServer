from typing import ClassVar

from labserver_contracts.common import TaskRequestStatus


class DomainError(Exception):
    code: ClassVar[str] = "domain_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidTransition(DomainError):
    code = "invalid_transition"

    def __init__(self, source: TaskRequestStatus, target: TaskRequestStatus) -> None:
        self.source = source
        self.target = target
        super().__init__(f"Request cannot transition from {source.value} to {target.value}")


class Forbidden(DomainError):
    code = "forbidden"


class ServerDisabled(DomainError):
    code = "server_disabled"


class CapacityExceeded(DomainError):
    code = "capacity_exceeded"

    def __init__(self, resource: str, requested: float, available: float) -> None:
        self.resource = resource
        self.requested = requested
        self.available = available
        super().__init__(
            f"Requested {resource} capacity {requested:g} exceeds available capacity {available:g}"
        )


class NotFound(DomainError):
    code = "not_found"


class DomainValidationError(DomainError):
    code = "validation_error"
