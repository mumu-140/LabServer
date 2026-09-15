from typing import Annotated, Self
from uuid import UUID

from pydantic import Field, StringConstraints, field_validator, model_validator

from .common import ReadModel, StrictWriteModel, TaskRequestStatus, UtcDateTime

TrimmedText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PositiveMinutes = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
NonNegativeFloat = Annotated[float, Field(ge=0)]
GpuId = Annotated[int, Field(ge=0)]


def _unique_gpu_ids(value: list[int] | None) -> list[int] | None:
    if value is not None and len(value) != len(set(value)):
        raise ValueError("GPU IDs must be unique")
    return value


class TaskRequestCreate(StrictWriteModel):
    title: TrimmedText
    project: TrimmedText | None = None
    preferred_server_id: UUID
    planned_start: UtcDateTime
    planned_duration_minutes: PositiveMinutes
    requested_cpu_cores: NonNegativeInt
    requested_memory_gb: NonNegativeFloat | None = None
    requested_gpu_count: NonNegativeInt
    preferred_gpu_ids: list[GpuId] | None = None
    note: TrimmedText | None = None

    _validate_unique_gpu_ids = field_validator("preferred_gpu_ids")(_unique_gpu_ids)

    @model_validator(mode="after")
    def validate_gpu_count(self) -> Self:
        if (
            self.preferred_gpu_ids is not None
            and self.requested_gpu_count != len(self.preferred_gpu_ids)
        ):
            raise ValueError("requested_gpu_count must equal the number of preferred GPU IDs")
        return self


class TaskRequestUpdate(StrictWriteModel):
    title: TrimmedText | None = None
    project: TrimmedText | None = None
    preferred_server_id: UUID | None = None
    planned_start: UtcDateTime | None = None
    planned_duration_minutes: PositiveMinutes | None = None
    requested_cpu_cores: NonNegativeInt | None = None
    requested_memory_gb: NonNegativeFloat | None = None
    requested_gpu_count: NonNegativeInt | None = None
    preferred_gpu_ids: list[GpuId] | None = None
    note: TrimmedText | None = None

    _validate_unique_gpu_ids = field_validator("preferred_gpu_ids")(_unique_gpu_ids)

    @model_validator(mode="after")
    def validate_gpu_count(self) -> Self:
        if (
            self.preferred_gpu_ids is not None
            and self.requested_gpu_count is not None
            and self.requested_gpu_count != len(self.preferred_gpu_ids)
        ):
            raise ValueError("requested_gpu_count must equal the number of preferred GPU IDs")
        return self


class TaskRequestRead(ReadModel):
    id: UUID
    requester_id: UUID
    title: str
    project: str | None
    preferred_server_id: UUID
    planned_start: UtcDateTime
    planned_duration_minutes: int
    requested_cpu_cores: int
    requested_memory_gb: float | None
    requested_gpu_count: int
    preferred_gpu_ids: list[int] | None
    note: str | None
    status: TaskRequestStatus
    created_at: UtcDateTime
    updated_at: UtcDateTime
