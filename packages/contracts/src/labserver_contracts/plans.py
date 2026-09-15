"""Canonical simple-planning DTOs.

Planning means only: "I intend to use this server/resource during this window."
Publication is never gated, queued, or dispatched on this contract surface.
"""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Self
from uuid import UUID

from pydantic import Field, model_validator

from .common import (
    ConflictCertainty,
    ConflictResource,
    ReadModel,
    StrictWriteModel,
    UtcDateTime,
)

GpuId = Annotated[int, Field(ge=0)]


class PlanDisplayState(StrEnum):
    """Derived from time only; never persisted as a lifecycle column."""

    CANCELLED = "cancelled"
    UPCOMING = "upcoming"
    ONGOING = "ongoing"
    PAST = "past"


def validate_plan_window(
    start_at: datetime | None,
    end_at: datetime | None,
    gpu_count: int | None,
    gpu_ids: tuple[int, ...] | list[int] | None,
) -> None:
    if start_at is not None and end_at is not None and end_at <= start_at:
        raise ValueError("end_at must be after start_at")
    if gpu_ids is not None:
        if len(set(gpu_ids)) != len(gpu_ids):
            raise ValueError("gpu_ids must be unique")
        if any(device < 0 for device in gpu_ids):
            raise ValueError("gpu_ids must be non-negative")
        if gpu_count is not None and gpu_count != len(gpu_ids):
            raise ValueError("gpu_count must match gpu_ids")


class PlanCreate(StrictWriteModel):
    server_id: UUID
    title: str = Field(min_length=1, max_length=200)
    project: str | None = Field(default=None, max_length=200)
    start_at: UtcDateTime
    end_at: UtcDateTime
    cpu_cores: int | None = Field(default=None, ge=1)
    memory_gb: float | None = Field(default=None, gt=0)
    gpu_count: int | None = Field(default=None, ge=0)
    gpu_ids: tuple[GpuId, ...] | None = None
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_plan(self) -> Self:
        validate_plan_window(self.start_at, self.end_at, self.gpu_count, self.gpu_ids)
        return self


class PlanUpdate(StrictWriteModel):
    """Mutable intent fields only; ownership is never client-settable."""

    server_id: UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    project: str | None = Field(default=None, max_length=200)
    start_at: UtcDateTime | None = None
    end_at: UtcDateTime | None = None
    cpu_cores: int | None = Field(default=None, ge=1)
    memory_gb: float | None = Field(default=None, gt=0)
    gpu_count: int | None = Field(default=None, ge=0)
    gpu_ids: tuple[GpuId, ...] | None = None
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_plan(self) -> Self:
        validate_plan_window(self.start_at, self.end_at, self.gpu_count, self.gpu_ids)
        return self


class PlanRead(ReadModel):
    id: UUID
    owner_id: UUID
    server_id: UUID
    title: str
    project: str | None
    start_at: UtcDateTime
    end_at: UtcDateTime
    cpu_cores: int | None
    memory_gb: float | None
    gpu_count: int | None
    gpu_ids: tuple[GpuId, ...] | None
    note: str | None
    cancelled_at: UtcDateTime | None
    created_at: UtcDateTime
    updated_at: UtcDateTime
    display_state: PlanDisplayState


class PlanConflictRead(ReadModel):
    """Advisory overlap warning; it never blocks create or update."""

    resource: ConflictResource
    certainty: ConflictCertainty
    start_at: UtcDateTime
    end_at: UtcDateTime
    requested: float | tuple[int, ...]
    available: float | tuple[int, ...] | None
    conflicting_plan_ids: tuple[UUID, ...]
    reason: str
