from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict


class UserRole(StrEnum):
    ADMIN = "admin"
    MEMBER = "member"


class TaskRequestStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class ReservationStatus(StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ReservationSource(StrEnum):
    REQUEST = "request"
    ADMIN = "admin"


class ConflictCertainty(StrEnum):
    CONFIRMED = "confirmed"
    UNCERTAIN = "uncertain"


class ConflictResource(StrEnum):
    CPU = "cpu"
    MEMORY = "memory"
    GPU = "gpu"
    GPU_DEVICE = "gpu_device"


def _normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include a timezone")
    return value.astimezone(UTC)


UtcDateTime = Annotated[datetime, AfterValidator(_normalize_utc)]


class StrictWriteModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReadModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ErrorDetail(ReadModel):
    code: str
    message: str


class ErrorResponse(ReadModel):
    error: ErrorDetail
