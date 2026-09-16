"""Persistence-level tests for auth sessions and the 0003 migration."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from labserver_contracts.common import UserRole
from labserver_core.domain.entities import AuthSession, User
from labserver_core.persistence.database import create_engine_and_session_factory
from labserver_core.persistence.unit_of_work import SqlAlchemyUnitOfWork
from sqlalchemy import create_engine, inspect

CORE_DIR = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 9, 16, 8, 0, tzinfo=UTC)

AUTH_SESSION_COLUMNS = {"token_hash", "user_id", "created_at", "expires_at"}


def upgrade_database(database_url: str, revision: str = "head") -> None:
    """Run alembic with driver-level autocommit (see test_migrations.py)."""
    config = Config(str(CORE_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    config.set_main_option("sqlalchemy.isolation_level", "AUTOCOMMIT")
    command.upgrade(config, revision)


def _user(password_hash: str | None) -> User:
    return User(
        id=uuid4(),
        username="alice",
        display_name="Alice",
        role=UserRole.MEMBER,
        enabled=True,
        created_at=NOW,
        updated_at=NOW,
        password_hash=password_hash,
    )


def test_migration_head_creates_auth_sessions_and_password_hash(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'auth-schema.sqlite'}"
    upgrade_database(database_url)

    inspector = inspect(create_engine(database_url))
    assert "auth_sessions" in inspector.get_table_names()
    session_columns = {column["name"] for column in inspector.get_columns("auth_sessions")}
    assert session_columns == AUTH_SESSION_COLUMNS

    user_columns = {column["name"] for column in inspector.get_columns("users")}
    assert "password_hash" in user_columns
    nullable = {
        column["name"]: column["nullable"] for column in inspector.get_columns("users")
    }
    assert nullable["password_hash"] is True


def test_migration_0002_to_0003_adds_auth_schema(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'incremental.sqlite'}"
    upgrade_database(database_url, revision="0002_simple_planning")
    inspector = inspect(create_engine(database_url))
    assert "auth_sessions" not in inspector.get_table_names()
    assert "password_hash" not in {
        column["name"] for column in inspector.get_columns("users")
    }

    upgrade_database(database_url, revision="0003_auth")
    inspector = inspect(create_engine(database_url))
    assert {column["name"] for column in inspector.get_columns("auth_sessions")} == (
        AUTH_SESSION_COLUMNS
    )


def test_session_repository_round_trip_and_expiry(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'sessions.sqlite'}"
    upgrade_database(database_url)
    _, session_factory = create_engine_and_session_factory(database_url)

    user = _user(password_hash=None)
    active = AuthSession(
        token_hash="a" * 64,
        user_id=user.id,
        created_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    expired = AuthSession(
        token_hash="b" * 64,
        user_id=user.id,
        created_at=NOW - timedelta(hours=2),
        expires_at=NOW - timedelta(hours=1),
    )

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.users.add(user)
        uow.commit()

    # Sessions are added in a separate unit of work: without an ORM
    # relationship the flush order between tables is not guaranteed.
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.auth_sessions.add(active)
        uow.auth_sessions.add(expired)
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        stored = uow.auth_sessions.get("a" * 64)
        assert stored is not None
        assert stored.user_id == user.id
        assert stored.expires_at == active.expires_at
        assert uow.auth_sessions.get("c" * 64) is None

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.auth_sessions.delete_expired(NOW) == 1
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.auth_sessions.get("b" * 64) is None
        assert uow.auth_sessions.get("a" * 64) is not None
        uow.auth_sessions.delete("a" * 64)
        uow.commit()
        assert uow.auth_sessions.get("a" * 64) is None


def test_session_token_hash_is_primary_key(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'pk.sqlite'}"
    upgrade_database(database_url)
    _, session_factory = create_engine_and_session_factory(database_url)

    user = _user(password_hash=None)
    duplicate = AuthSession(
        token_hash="d" * 64,
        user_id=user.id,
        created_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.users.add(user)
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.auth_sessions.add(duplicate)
        uow.auth_sessions.add(duplicate)
        try:
            uow.commit()
        except Exception:
            uow.rollback()
        else:
            raise AssertionError("duplicate token hash must violate the primary key")
