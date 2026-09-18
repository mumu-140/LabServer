from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi import HTTPException
from labserver_contracts.common import UserRole
from labserver_contracts.servers import ServerCreate, ServerUpdate
from labserver_contracts.users import UserCreate
from labserver_core.api.dependencies import get_current_actor
from labserver_core.application.actors import CurrentActor, require_admin, require_self_or_admin
from labserver_core.application.server_service import ServerService
from labserver_core.application.user_service import UserService
from labserver_core.domain.entities import ManagedServer, ServerCapacity, User
from labserver_core.domain.errors import DomainValidationError, Forbidden

NOW = datetime(2026, 9, 15, 6, 0, tzinfo=UTC)
ADMIN_ID = UUID("00000000-0000-0000-0000-000000000701")
MEMBER_ID = UUID("00000000-0000-0000-0000-000000000702")
SERVER_ID = UUID("00000000-0000-0000-0000-000000000703")
NEW_USER_ID = UUID("00000000-0000-0000-0000-000000000704")


class FakeUserRepository:
    def __init__(self, users: list[User]) -> None:
        self.items = {user.id: user for user in users}

    def get(self, user_id: UUID) -> User | None:
        return self.items.get(user_id)

    def get_by_username(self, username: str) -> User | None:
        return next((user for user in self.items.values() if user.username == username), None)

    def add(self, user: User) -> None:
        self.items[user.id] = user

    def list_all(self) -> list[User]:
        return sorted(self.items.values(), key=lambda user: user.username)


class FakeServerRepository:
    def __init__(self, servers: list[ManagedServer] | None = None) -> None:
        self.items = {server.id: server for server in servers or []}

    def get(self, server_id: UUID) -> ManagedServer | None:
        return self.items.get(server_id)

    def get_by_key(self, key: str) -> ManagedServer | None:
        return next((server for server in self.items.values() if server.key == key), None)

    def add(self, server: ManagedServer) -> None:
        self.items[server.id] = server

    def save(self, server: ManagedServer) -> None:
        self.items[server.id] = server

    def list_all(self) -> list[ManagedServer]:
        return sorted(self.items.values(), key=lambda server: server.key)


class FakeUnitOfWork:
    def __init__(self, users: FakeUserRepository, servers: FakeServerRepository) -> None:
        self.users = users
        self.servers = servers
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self) -> "FakeUnitOfWork":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def make_user(
    user_id: UUID,
    username: str,
    role: UserRole,
    *,
    enabled: bool = True,
) -> User:
    return User(user_id, username, username.title(), role, enabled, NOW, NOW)


def make_uow(
    *,
    admin_enabled: bool = True,
    member_enabled: bool = True,
    servers: list[ManagedServer] | None = None,
) -> FakeUnitOfWork:
    users = FakeUserRepository(
        [
            make_user(ADMIN_ID, "admin", UserRole.ADMIN, enabled=admin_enabled),
            make_user(MEMBER_ID, "member", UserRole.MEMBER, enabled=member_enabled),
        ]
    )
    return FakeUnitOfWork(users, FakeServerRepository(servers))


def fixed_id_factory() -> UUID:
    return SERVER_ID


def fixed_user_id_factory() -> UUID:
    return NEW_USER_ID


def fixed_clock() -> datetime:
    return NOW


def factory_for(uow: FakeUnitOfWork) -> Callable[[], FakeUnitOfWork]:
    return lambda: uow


def test_http_actor_dependency_is_default_deny() -> None:
    from starlette.requests import Request
    request = Request({"type": "http", "headers": []})
    with pytest.raises(HTTPException) as exc_info:
        get_current_actor(request, None)  # type: ignore[arg-type]

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Authentication required" 


def test_member_cannot_perform_admin_actions() -> None:
    member = CurrentActor(MEMBER_ID, UserRole.MEMBER)

    with pytest.raises(Forbidden):
        require_admin(member)

    with pytest.raises(Forbidden):
        require_self_or_admin(member, ADMIN_ID)

    require_self_or_admin(member, MEMBER_ID)


def test_member_cannot_create_or_disable_server() -> None:
    uow = make_uow(
        servers=[
            ManagedServer(
                SERVER_ID,
                "fwq10",
                "fwq10",
                True,
                ServerCapacity(64, 256.0, 4),
                NOW,
                NOW,
            )
        ]
    )
    service = ServerService(factory_for(uow), clock=fixed_clock, id_factory=fixed_id_factory)
    member = CurrentActor(MEMBER_ID, UserRole.MEMBER)

    with pytest.raises(Forbidden):
        service.create_server(
            member,
            ServerCreate(key="fwq51", display_name="fwq51", cpu_cores=32, gpu_count=2),
        )

    with pytest.raises(Forbidden):
        service.update_server(member, SERVER_ID, ServerUpdate(enabled=False))

    assert uow.commits == 0


def test_admin_can_create_and_update_logical_server() -> None:
    uow = make_uow()
    created_ids = iter(
        [SERVER_ID, UUID("00000000-0000-0000-0000-000000000705")]
    )
    service = ServerService(
        factory_for(uow), clock=fixed_clock, id_factory=lambda: next(created_ids)
    )
    admin = CurrentActor(ADMIN_ID, UserRole.ADMIN)

    server = service.create_server(
        admin,
        ServerCreate(
            key="fwq10",
            display_name="Compute 10",
            cpu_cores=64,
            memory_gb=256.0,
            gpu_count=4,
        ),
    )
    assert server.key == "fwq10"
    assert server.capacity == ServerCapacity(64, 256.0, 4)

    updated = service.update_server(
        admin,
        server.id,
        ServerUpdate(display_name="Compute 10A", enabled=False, gpu_count=None),
    )
    assert updated.display_name == "Compute 10A"
    assert updated.enabled is False
    assert updated.capacity.gpu_count is None
    assert uow.commits == 2


def test_duplicate_logical_server_key_is_rejected_before_commit() -> None:
    existing = ManagedServer(
        SERVER_ID,
        "fwq10",
        "fwq10",
        True,
        ServerCapacity(64, 256.0, 4),
        NOW,
        NOW,
    )
    uow = make_uow(servers=[existing])
    service = ServerService(factory_for(uow), clock=fixed_clock, id_factory=fixed_id_factory)

    with pytest.raises(DomainValidationError) as exc_info:
        service.create_server(
            CurrentActor(ADMIN_ID, UserRole.ADMIN),
            ServerCreate(key="fwq10", display_name="duplicate"),
        )

    assert exc_info.value.code == "validation_error"
    assert uow.commits == 0


def test_disabled_actor_is_rejected_by_application_boundary() -> None:
    uow = make_uow(member_enabled=False)
    service = ServerService(factory_for(uow), clock=fixed_clock, id_factory=fixed_id_factory)

    with pytest.raises(Forbidden):
        service.list_servers(CurrentActor(MEMBER_ID, UserRole.MEMBER))


def test_actor_role_must_match_persisted_role() -> None:
    uow = make_uow()
    service = ServerService(factory_for(uow), clock=fixed_clock, id_factory=fixed_id_factory)

    with pytest.raises(Forbidden):
        service.list_servers(CurrentActor(MEMBER_ID, UserRole.ADMIN))


def test_admin_can_create_and_list_users() -> None:
    uow = make_uow()
    service = UserService(
        factory_for(uow),
        clock=fixed_clock,
        id_factory=fixed_user_id_factory,
    )
    admin = CurrentActor(ADMIN_ID, UserRole.ADMIN)

    created = service.create_user(
        admin,
        UserCreate(username="scientist", display_name="Scientist", role=UserRole.MEMBER),
    )

    assert created.id == NEW_USER_ID
    assert created.username == "scientist"
    assert {user.username for user in service.list_users(admin)} == {
        "admin",
        "member",
        "scientist",
    }
    assert uow.commits == 1


def test_duplicate_username_is_rejected() -> None:
    uow = make_uow()
    service = UserService(
        factory_for(uow),
        clock=fixed_clock,
        id_factory=fixed_user_id_factory,
    )

    with pytest.raises(DomainValidationError):
        service.create_user(
            CurrentActor(ADMIN_ID, UserRole.ADMIN),
            UserCreate(username="member", display_name="Duplicate"),
        )


def test_active_member_can_list_users() -> None:
    uow = make_uow()
    service = UserService(
        factory_for(uow),
        clock=fixed_clock,
        id_factory=fixed_user_id_factory,
    )
    member = CurrentActor(MEMBER_ID, UserRole.MEMBER)

    users = service.list_users(member)

    assert {user.username for user in users} == {"admin", "member"}
