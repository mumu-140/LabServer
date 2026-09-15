from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from labserver_contracts.common import (
    ReservationSource,
    ReservationStatus,
    TaskRequestStatus,
    UserRole,
)
from labserver_core.domain.entities import (
    ManagedServer,
    Reservation,
    ServerCapacity,
    TaskRequest,
    User,
)
from labserver_core.persistence.database import create_engine_and_session_factory
from labserver_core.persistence.repositories import (
    RequestRepository,
    ReservationRepository,
    ServerRepository,
    UserRepository,
)
from labserver_core.persistence.unit_of_work import SqlAlchemyUnitOfWork
from sqlalchemy import MetaData, Table, create_engine, inspect
from sqlalchemy.exc import IntegrityError

CORE_DIR = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 9, 15, 5, 0, tzinfo=UTC)
START = datetime(2026, 9, 18, 0, 0, tzinfo=UTC)


def upgrade_database(database_url: str) -> None:
    config = Config(str(CORE_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


def test_initial_migration_creates_expected_schema_and_no_private_endpoint(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'schema.sqlite'}"
    upgrade_database(database_url)

    engine = create_engine(database_url)
    inspector = inspect(engine)

    assert set(inspector.get_table_names()) >= {
        "users",
        "managed_servers",
        "task_requests",
        "reservations",
        "audit_events",
        "alembic_version",
    }
    server_columns = {column["name"] for column in inspector.get_columns("managed_servers")}
    assert "ip" not in server_columns
    assert "endpoint" not in server_columns
    assert {"key", "cpu_cores", "memory_gb", "gpu_count"} <= server_columns


def test_sqlite_foreign_keys_are_enforced_after_migration(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'foreign-keys.sqlite'}"
    upgrade_database(database_url)
    engine, _ = create_engine_and_session_factory(database_url)

    metadata = MetaData()
    task_requests = Table("task_requests", metadata, autoload_with=engine)

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            task_requests.insert().values(
                id=uuid4().hex,
                title="orphan request",
                requester_id=uuid4().hex,
                project=None,
                preferred_server_id=uuid4().hex,
                planned_start=START,
                planned_duration_minutes=60,
                requested_cpu_cores=1,
                requested_memory_gb=None,
                requested_gpu_count=0,
                preferred_gpu_ids=None,
                note=None,
                status=TaskRequestStatus.DRAFT.value,
                status_changed_by=None,
                created_at=NOW,
                updated_at=NOW,
            )
        )


def test_repositories_round_trip_domain_entities(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'repositories.sqlite'}"
    upgrade_database(database_url)
    _, session_factory = create_engine_and_session_factory(database_url)

    user = User(
        id=UUID("00000000-0000-0000-0000-000000000201"),
        username="alice",
        display_name="Alice",
        role=UserRole.MEMBER,
        enabled=True,
        created_at=NOW,
        updated_at=NOW,
    )
    server = ManagedServer(
        id=UUID("00000000-0000-0000-0000-000000000301"),
        key="fwq10",
        display_name="fwq10",
        enabled=True,
        capacity=ServerCapacity(cpu_cores=64, memory_gb=256.0, gpu_count=4),
        created_at=NOW,
        updated_at=NOW,
    )
    task_request = TaskRequest(
        id=UUID("00000000-0000-0000-0000-000000000401"),
        requester_id=user.id,
        title="Poplar assembly",
        project="Populus",
        preferred_server_id=server.id,
        planned_start=START,
        planned_duration_minutes=120,
        requested_cpu_cores=32,
        requested_memory_gb=128.0,
        requested_gpu_count=2,
        preferred_gpu_ids=(0, 1),
        note=None,
        status=TaskRequestStatus.SUBMITTED,
        created_at=NOW,
        updated_at=NOW,
    )
    reservation = Reservation(
        id=UUID("00000000-0000-0000-0000-000000000501"),
        request_id=task_request.id,
        owner_id=user.id,
        server_id=server.id,
        title=task_request.title,
        start_at=START,
        end_at=START + timedelta(minutes=120),
        cpu_cores=32,
        memory_gb=128.0,
        gpu_count=2,
        gpu_ids=(0, 1),
        status=ReservationStatus.PLANNED,
        source=ReservationSource.REQUEST,
        created_at=NOW,
        updated_at=NOW,
    )

    with session_factory() as session:
        users = UserRepository(session)
        servers = ServerRepository(session)
        requests = RequestRepository(session)
        reservations = ReservationRepository(session)
        users.add(user)
        servers.add(server)
        session.commit()
        requests.add(task_request)
        session.commit()
        reservations.add(reservation)
        session.commit()

    with session_factory() as session:
        assert UserRepository(session).get(user.id) == user
        assert ServerRepository(session).get_by_key("fwq10") == server
        assert RequestRepository(session).get(task_request.id) == task_request
        assert ReservationRepository(session).get_by_request_id(task_request.id) == reservation
        assert RequestRepository(session).list_for_user(user.id) == [task_request]


def test_reservation_window_query_uses_half_open_overlap(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'window.sqlite'}"
    upgrade_database(database_url)
    _, session_factory = create_engine_and_session_factory(database_url)

    user_id = UUID("00000000-0000-0000-0000-000000000201")
    server_id = UUID("00000000-0000-0000-0000-000000000301")
    with session_factory() as session:
        UserRepository(session).add(
            User(user_id, "alice", "Alice", UserRole.MEMBER, True, NOW, NOW)
        )
        ServerRepository(session).add(
            ManagedServer(
                server_id,
                "fwq10",
                "fwq10",
                True,
                ServerCapacity(64, 256.0, 4),
                NOW,
                NOW,
            )
        )
        session.commit()
        repo = ReservationRepository(session)
        repo.add(
            Reservation(
                uuid4(),
                None,
                user_id,
                server_id,
                "first",
                START,
                START + timedelta(hours=1),
                4,
                8.0,
                1,
                (0,),
                ReservationStatus.PLANNED,
                ReservationSource.ADMIN,
                NOW,
                NOW,
            )
        )
        repo.add(
            Reservation(
                uuid4(),
                None,
                user_id,
                server_id,
                "second",
                START + timedelta(hours=1),
                START + timedelta(hours=2),
                4,
                8.0,
                1,
                (1,),
                ReservationStatus.PLANNED,
                ReservationSource.ADMIN,
                NOW,
                NOW,
            )
        )
        session.commit()

    with session_factory() as session:
        repo = ReservationRepository(session)
        first_window = repo.list_for_server(server_id, START, START + timedelta(hours=1))
        second_window = repo.list_for_server(
            server_id, START + timedelta(hours=1), START + timedelta(hours=2)
        )

    assert [reservation.title for reservation in first_window] == ["first"]
    assert [reservation.title for reservation in second_window] == ["second"]


def test_unit_of_work_rolls_back_on_exception(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'uow.sqlite'}"
    upgrade_database(database_url)
    _, session_factory = create_engine_and_session_factory(database_url)
    user = User(
        UUID("00000000-0000-0000-0000-000000000601"),
        "rollback-user",
        "Rollback User",
        UserRole.MEMBER,
        True,
        NOW,
        NOW,
    )

    with pytest.raises(RuntimeError), SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.users.add(user)
        raise RuntimeError("force rollback")

    with session_factory() as session:
        assert UserRepository(session).get(user.id) is None


def test_unit_of_work_commit_persists_changes(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'uow-commit.sqlite'}"
    upgrade_database(database_url)
    _, session_factory = create_engine_and_session_factory(database_url)
    user = User(
        UUID("00000000-0000-0000-0000-000000000602"),
        "commit-user",
        "Commit User",
        UserRole.MEMBER,
        True,
        NOW,
        NOW,
    )

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.users.add(user)
        uow.commit()

    with session_factory() as session:
        assert UserRepository(session).get(user.id) == user
