from typing import Annotated
from uuid import UUID

from pydantic import Field, field_validator

from .common import (
    ConflictCertainty,
    ConflictResource,
    ReadModel,
    ReservationSource,
    ReservationStatus,
    UtcDateTime,
)

GpuId = Annotated[int, Field(ge=0)]


def _unique_gpu_ids(value: list[int] | None) -> list[int] | None:
    if value is not None and len(value) != len(set(value)):
        raise ValueError("GPU IDs must be unique")
    return value


class ReservationRead(ReadModel):
    id: UUID
    request_id: UUID | None
    owner_id: UUID
    server_id: UUID
    title: str
    start_at: UtcDateTime
    end_at: UtcDateTime
    cpu_cores: int
    memory_gb: float | None
    gpu_count: int
    gpu_ids: list[GpuId] | None
    status: ReservationStatus
    source: ReservationSource
    created_at: UtcDateTime
    updated_at: UtcDateTime

    _validate_unique_gpu_ids = field_validator("gpu_ids")(_unique_gpu_ids)


class ConflictRead(ReadModel):
    resource: ConflictResource
    certainty: ConflictCertainty
    start_at: UtcDateTime
    end_at: UtcDateTime
    requested: float | list[int]
    available: float | list[int] | None
    conflicting_reservation_ids: list[UUID]
    reason: str
