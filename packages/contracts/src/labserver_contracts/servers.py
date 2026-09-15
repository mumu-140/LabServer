from typing import Annotated
from uuid import UUID

from pydantic import Field, StringConstraints

from .common import ReadModel, StrictWriteModel, UtcDateTime

ServerKey = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, pattern=r"^[A-Za-z0-9._-]+$"),
]
TrimmedText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PositiveInt = Annotated[int, Field(gt=0)]
PositiveFloat = Annotated[float, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]


class ServerCreate(StrictWriteModel):
    key: ServerKey
    display_name: TrimmedText
    enabled: bool = True
    cpu_cores: PositiveInt | None = None
    memory_gb: PositiveFloat | None = None
    gpu_count: NonNegativeInt | None = None


class ServerUpdate(StrictWriteModel):
    display_name: TrimmedText | None = None
    enabled: bool | None = None
    cpu_cores: PositiveInt | None = None
    memory_gb: PositiveFloat | None = None
    gpu_count: NonNegativeInt | None = None


class ServerRead(ReadModel):
    id: UUID
    key: str
    display_name: str
    enabled: bool
    cpu_cores: int | None
    memory_gb: float | None
    gpu_count: int | None
    created_at: UtcDateTime
    updated_at: UtcDateTime
