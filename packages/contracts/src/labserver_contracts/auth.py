from typing import Annotated
from uuid import UUID

from pydantic import StringConstraints

from .common import ReadModel, StrictWriteModel, UserRole
from .users import TrimmedText

LoginPassword = Annotated[str, StringConstraints(min_length=1)]
NewPassword = Annotated[str, StringConstraints(min_length=8)]


class LoginRequest(StrictWriteModel):
    username: TrimmedText
    password: LoginPassword


class SessionRead(ReadModel):
    user_id: UUID
    role: UserRole


class UserPasswordSet(StrictWriteModel):
    password: NewPassword
