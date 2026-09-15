from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from labserver_contracts.common import (
    ReservationSource,
    ReservationStatus,
    TaskRequestStatus,
    UserRole,
)


@dataclass(frozen=True, slots=True)
class User:
    id: UUID
    username: str
    display_name: str
    role: UserRole
    enabled: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ServerCapacity:
    cpu_cores: int | None
    memory_gb: float | None
    gpu_count: int | None


@dataclass(frozen=True, slots=True)
class ManagedServer:
    id: UUID
    key: str
    display_name: str
    enabled: bool
    capacity: ServerCapacity
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class TaskRequest:
    id: UUID
    requester_id: UUID
    title: str
    project: str | None
    preferred_server_id: UUID
    planned_start: datetime
    planned_duration_minutes: int
    requested_cpu_cores: int
    requested_memory_gb: float | None
    requested_gpu_count: int
    preferred_gpu_ids: tuple[int, ...] | None
    note: str | None
    status: TaskRequestStatus
    created_at: datetime
    updated_at: datetime
    status_changed_by: UUID | None = None


@dataclass(frozen=True, slots=True)
class Reservation:
    id: UUID
    request_id: UUID | None
    owner_id: UUID
    server_id: UUID
    title: str
    start_at: datetime
    end_at: datetime
    cpu_cores: int
    memory_gb: float | None
    gpu_count: int
    gpu_ids: tuple[int, ...] | None
    status: ReservationStatus
    source: ReservationSource
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AuditEvent:
    id: UUID
    entity_type: str
    entity_id: UUID
    action: str
    actor_id: UUID | None
    occurred_at: datetime
    details: dict[str, object] | None = None
