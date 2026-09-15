from typing import Annotated
from uuid import UUID

from pydantic import StringConstraints

from .common import ReadModel, StrictWriteModel, UserRole, UtcDateTime

TrimmedText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class UserCreate(StrictWriteModel):
    username: TrimmedText
    display_name: TrimmedText
    role: UserRole = UserRole.MEMBER
    enabled: bool = True


class UserRead(ReadModel):
    id: UUID
    username: str
    display_name: str
    role: UserRole
    enabled: bool
    created_at: UtcDateTime
    updated_at: UtcDateTime
