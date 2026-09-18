from uuid import uuid4

import pytest
from labserver_contracts.auth import LoginRequest, SessionRead
from labserver_contracts.common import UserRole
from labserver_contracts.users import UserPasswordSet
from pydantic import ValidationError


def test_login_request_accepts_trimmed_credentials() -> None:
    request = LoginRequest(username="  alice  ", password="secret")
    assert request.username == "alice"
    assert request.password == "secret"


def test_login_request_rejects_blank_username() -> None:
    with pytest.raises(ValidationError):
        LoginRequest(username="   ", password="secret")


def test_login_request_rejects_short_password() -> None:
    with pytest.raises(ValidationError):
        LoginRequest(username="alice", password="")


def test_login_request_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        LoginRequest.model_validate({"username": "alice", "password": "s", "role": "admin"})


def test_session_read_round_trip() -> None:
    user_id = uuid4()
    session = SessionRead(user_id=user_id, role=UserRole.MEMBER)
    payload = session.model_dump(mode="json")
    restored = SessionRead.model_validate(payload)
    assert restored.user_id == user_id
    assert restored.role is UserRole.MEMBER


def test_user_password_set_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        UserPasswordSet.model_validate({"password": "secret", "username": "alice"})
