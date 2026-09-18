from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from labserver_contracts.common import UserRole
from labserver_core.application.actors import CurrentActor
from labserver_core.application.auth_service import AuthService, SessionContext
from labserver_core.config import Settings
from labserver_core.domain.entities import AuthSession, User
from labserver_core.domain.errors import Forbidden, NotFound, UnknownCredentials

NOW = datetime(2026, 9, 17, 8, 0, tzinfo=UTC)
ADMIN_ID = UUID("00000000-0000-0000-0000-000000000101")
MEMBER_ID = UUID("00000000-0000-0000-0000-000000000102")
DISABLED_ID = UUID("00000000-0000-0000-0000-000000000103")
NOPW_ID = UUID("00000000-0000-0000-0000-000000000104")


class FakeUsers:
    def __init__(self, users: list[User]) -> None:
        self.items = {u.id: u for u in users}

    def get(self, user_id: UUID) -> User | None:
        return self.items.get(user_id)

    def get_by_username(self, username: str) -> User | None:
        for u in self.items.values():
            if u.username == username:
                return u
        return None

    def add(self, user: User) -> None:
        self.items[user.id] = user

    def list_all(self) -> list[User]:
        return list(self.items.values())

    def set_password_hash(self, user_id: UUID, password_hash: str) -> None:
        u = self.items[user_id]
        self.items[user_id] = replace(u, password_hash=password_hash)


class FakeAuthSessions:
    def __init__(self) -> None:
        self.items: dict[str, AuthSession] = {}

    def add(self, session_record: AuthSession) -> None:
        self.items[session_record.token_hash] = session_record

    def get(self, token_hash: str) -> AuthSession | None:
        return self.items.get(token_hash)

    def delete(self, token_hash: str) -> None:
        self.items.pop(token_hash, None)

    def delete_expired(self, now: datetime) -> int:
        expired = [k for k, v in self.items.items() if v.expires_at <= now]
        for k in expired:
            del self.items[k]
        return len(expired)


class FakeUow:
    def __init__(self, users: FakeUsers, sessions: FakeAuthSessions) -> None:
        self.users = users
        self.auth_sessions = sessions
        self.committed = False

    def __enter__(self) -> "FakeUow":
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        pass

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        pass


class FakePasswordHasher:
    def hash(self, raw: str) -> str:
        return f"hashed:{raw}"

    def verify(self, raw: str, encoded: str) -> bool:
        return encoded == f"hashed:{raw}"


def _make_env(
    *,
    ttl_hours: int = 168,
    clock: Callable[[], datetime] = lambda: NOW,
) -> tuple[AuthService, FakeUsers, FakeAuthSessions, FakeUow]:
    users = FakeUsers(
        [
            User(
                id=ADMIN_ID,
                username="admin",
                display_name="Admin",
                role=UserRole.ADMIN,
                enabled=True,
                created_at=NOW,
                updated_at=NOW,
                password_hash="hashed:adminpass",
            ),
            User(
                id=MEMBER_ID,
                username="member",
                display_name="Member",
                role=UserRole.MEMBER,
                enabled=True,
                created_at=NOW,
                updated_at=NOW,
                password_hash="hashed:memberpass",
            ),
            User(
                id=DISABLED_ID,
                username="disabled",
                display_name="Disabled",
                role=UserRole.MEMBER,
                enabled=False,
                created_at=NOW,
                updated_at=NOW,
                password_hash="hashed:disabledpass",
            ),
            User(
                id=NOPW_ID,
                username="nopw",
                display_name="No Password",
                role=UserRole.MEMBER,
                enabled=True,
                created_at=NOW,
                updated_at=NOW,
                password_hash=None,
            ),
        ]
    )
    sessions = FakeAuthSessions()
    uow = FakeUow(users, sessions)
    settings = Settings(database_url="sqlite:///:memory:", session_ttl_hours=ttl_hours)
    service = AuthService(
        uow_factory=lambda: uow,
        hasher=FakePasswordHasher(),
        settings=settings,
        clock=clock,
        token_factory=lambda: "fixed-test-token-12345",
    )
    return service, users, sessions, uow


def test_login_success():
    service, _, sessions, uow = _make_env()
    ctx = service.login("member", "memberpass")

    assert isinstance(ctx, SessionContext)
    assert ctx.raw_token == "fixed-test-token-12345"
    assert ctx.user_id == MEMBER_ID
    assert ctx.role == UserRole.MEMBER
    assert uow.committed is True

    stored = list(sessions.items.values())
    assert len(stored) == 1
    assert stored[0].user_id == MEMBER_ID
    assert stored[0].created_at == NOW
    assert stored[0].expires_at == NOW + timedelta(hours=168)


@pytest.mark.parametrize(
    ("username", "password"),
    [
        ("unknown", "memberpass"),
        ("member", "wrongpass"),
        ("disabled", "disabledpass"),
        ("nopw", "anything"),
    ],
)
def test_login_uniform_failure(username, password):
    service, _, _, _ = _make_env()
    with pytest.raises(UnknownCredentials) as exc_info:
        service.login(username, password)
    assert exc_info.value.code == "unauthorized"
    assert exc_info.value.message == "Invalid username or password"


def test_resolve_success():
    service, _, _, _ = _make_env()
    ctx = service.login("member", "memberpass")

    actor = service.resolve(ctx.raw_token)
    assert isinstance(actor, CurrentActor)
    assert actor.user_id == MEMBER_ID
    assert actor.role == UserRole.MEMBER


def test_resolve_unknown_token():
    service, _, _, _ = _make_env()
    with pytest.raises(UnknownCredentials) as exc_info:
        service.resolve("non-existent-token")
    assert exc_info.value.code == "unauthorized"


def test_resolve_expired_token():
    current_time = NOW
    service, _, _, _ = _make_env(clock=lambda: current_time)
    ctx = service.login("member", "memberpass")

    current_time = NOW + timedelta(hours=168, seconds=1)
    with pytest.raises(UnknownCredentials) as exc_info:
        service.resolve(ctx.raw_token)
    assert exc_info.value.code == "unauthorized"


def test_resolve_disabled_mid_session():
    service, users, _, _ = _make_env()
    ctx = service.login("member", "memberpass")

    u = users.get(MEMBER_ID)
    assert u is not None
    users.items[MEMBER_ID] = replace(u, enabled=False)

    with pytest.raises(Forbidden):
        service.resolve(ctx.raw_token)


def test_logout_invalidates_session():
    service, _, sessions, _ = _make_env()
    ctx = service.login("member", "memberpass")
    assert len(sessions.items) == 1

    service.logout(ctx.raw_token)
    assert len(sessions.items) == 0

    with pytest.raises(UnknownCredentials):
        service.resolve(ctx.raw_token)


def test_logout_idempotent():
    service, _, _, _ = _make_env()
    service.logout("unknown-token")  # Should not raise


def test_has_enabled_admin():
    service, users, _, _ = _make_env()
    assert service.has_enabled_admin() is True

    admin = users.get(ADMIN_ID)
    assert admin is not None
    users.items[ADMIN_ID] = replace(admin, enabled=False)
    assert service.has_enabled_admin() is False


def test_set_password_by_admin():
    service, users, _, uow = _make_env()
    admin_actor = CurrentActor(user_id=ADMIN_ID, role=UserRole.ADMIN)

    service.set_password(admin_actor, MEMBER_ID, "new-secret-123")

    updated = users.get(MEMBER_ID)
    assert updated is not None
    assert updated.password_hash == "hashed:new-secret-123"
    assert uow.committed is True


def test_set_password_forbidden_for_member():
    service, _, _, _ = _make_env()
    member_actor = CurrentActor(user_id=MEMBER_ID, role=UserRole.MEMBER)

    with pytest.raises(Forbidden):
        service.set_password(member_actor, MEMBER_ID, "new-secret-123")


def test_set_password_target_not_found():
    service, _, _, _ = _make_env()
    admin_actor = CurrentActor(user_id=ADMIN_ID, role=UserRole.ADMIN)

    with pytest.raises(NotFound):
        service.set_password(admin_actor, uuid4(), "new-secret-123")


def test_custom_session_ttl_honored():
    service, _, sessions, _ = _make_env(ttl_hours=48)
    _ = service.login("member", "memberpass")

    stored = list(sessions.items.values())
    assert stored[0].expires_at == NOW + timedelta(hours=48)
