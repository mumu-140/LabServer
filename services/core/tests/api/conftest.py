from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from labserver_contracts.common import UserRole
from labserver_core.api.dependencies import get_current_actor
from labserver_core.app import create_app
from labserver_core.application.actors import CurrentActor
from labserver_core.config import Settings
from labserver_core.domain.entities import ManagedServer, ServerCapacity, User
from labserver_core.persistence.repositories import ServerRepository, UserRepository
from sqlalchemy.orm import Session, sessionmaker

CORE_DIR = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 9, 15, 9, 0, tzinfo=UTC)
ADMIN_ID = UUID("00000000-0000-0000-0000-000000001001")
MEMBER_ID = UUID("00000000-0000-0000-0000-000000001002")
OTHER_ID = UUID("00000000-0000-0000-0000-000000001003")
SERVER_ID = UUID("00000000-0000-0000-0000-000000001004")


@dataclass
class ApiContext:
    app: FastAPI
    client: TestClient
    session_factory: sessionmaker[Session]

    def act_as(self, user_id: UUID, role: UserRole) -> None:
        actor = CurrentActor(user_id, role)
        self.app.dependency_overrides[get_current_actor] = lambda: actor

    def clear_actor(self) -> None:
        self.app.dependency_overrides.pop(get_current_actor, None)


def upgrade_database(database_url: str) -> None:
    config = Config(str(CORE_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    # Driver-level autocommit: the pysqlite legacy isolation loses the alembic
    # version stamp and post-DML DDL when the connection closes; see
    # tests/persistence/test_migrations.py.
    config.set_main_option("sqlalchemy.isolation_level", "AUTOCOMMIT")
    command.upgrade(config, "head")


@pytest.fixture
def api_context(tmp_path: Path) -> ApiContext:
    database_url = f"sqlite:///{tmp_path / 'api.sqlite'}"
    upgrade_database(database_url)
    app = create_app(Settings(database_url=database_url))
    session_factory = app.state.session_factory

    with session_factory() as session:
        users = UserRepository(session)
        users.add(User(ADMIN_ID, "admin", "Admin", UserRole.ADMIN, True, NOW, NOW))
        users.add(User(MEMBER_ID, "member", "Member", UserRole.MEMBER, True, NOW, NOW))
        users.add(User(OTHER_ID, "other", "Other", UserRole.MEMBER, True, NOW, NOW))
        ServerRepository(session).add(
            ManagedServer(
                SERVER_ID,
                "fwq10",
                "fwq10",
                True,
                ServerCapacity(64, 256.0, 4),
                NOW,
                NOW,
            )
        )
        session.commit()

    with TestClient(app) as client:
        yield ApiContext(app=app, client=client, session_factory=session_factory)
