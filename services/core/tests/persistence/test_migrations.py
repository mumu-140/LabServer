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
    PlanEntry,
    Reservation,
    ServerCapacity,
    TaskRequest,
    User,
)
from labserver_core.persistence.database import create_engine_and_session_factory
from labserver_core.persistence.repositories import (
    PlanRepository,
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
PLAN_ENTRY_COLUMNS = {
    "id",
    "owner_id",
    "server_id",
    "title",
    "project",
    "start_at",
    "end_at",
    "cpu_cores",
    "memory_gb",
    "gpu_count",
    "gpu_ids",
    "note",
    "cancelled_at",
    "created_at",
    "updated_at",
}


def upgrade_database(database_url: str, revision: str = "head") -> None:
    """Run alembic with driver-level autocommit.

    The pysqlite driver's legacy isolation auto-commits DDL but keeps DML (and
    any DDL executed after a DML statement) inside a driver transaction that is
    rolled back when the connection closes without an explicit commit; that
    would lose alembic's version stamp and drop the later migrations' DDL.
    Driver-level autocommit makes every migration statement persist, matching
    normal commit-on-success semantics.
    """
    config = Config(str(CORE_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    config.set_main_option("sqlalchemy.isolation_level", "AUTOCOMMIT")
    command.upgrade(config, revision)


def test_migration_head_creates_plan_entries_and_drops_legacy_tables(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'schema.sqlite'}"
    upgrade_database(database_url)

    engine = create_engine(database_url)
    inspector = inspect(engine)

    assert set(inspector.get_table_names()) >= {
        "users",
        "managed_servers",
        "plan_entries",
        "audit_events",
        "alembic_version",
    }
    assert "task_requests" not in inspector.get_table_names()
    assert "reservations" not in inspector.get_table_names()

    plan_columns = {column["name"] for column in inspector.get_columns("plan_entries")}
    assert plan_columns == PLAN_ENTRY_COLUMNS

    server_columns = {column["name"] for column in inspector.get_columns("managed_servers")}
    assert "ip" not in server_columns
    assert "endpoint" not in server_columns
    assert {"key", "cpu_cores", "memory_gb", "gpu_count"} <= server_columns


def test_sqlite_foreign_keys_are_enforced_after_migration(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'foreign-keys.sqlite'}"
    upgrade_database(database_url)
    engine, _ = create_engine_and_session_factory(database_url)

    metadata = MetaData()
    plan_entries = Table("plan_entries", metadata, autoload_with=engine)

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            plan_entries.insert().values(
                id=uuid4().hex,
                owner_id=uuid4().hex,
                server_id=uuid4().hex,
                title="orphan plan",
                project=None,
                start_at=START,
                end_at=START + timedelta(hours=1),
                cpu_cores=None,
                memory_gb=None,
                gpu_count=None,
                gpu_ids=None,
                note=None,
                cancelled_at=None,
                created_at=NOW,
                updated_at=NOW,
            )
        )


def test_migrated_reservations_become_plan_entries(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'migrate.sqlite'}"
    upgrade_database(database_url, revision="0001_initial_core")
    _, session_factory = create_engine_and_session_factory(database_url)

    user = User(
        UUID("00000000-0000-0000-0000-000000000201"),
        "alice",
        "Alice",
        UserRole.MEMBER,
        True,
        NOW,
        NOW,
    )
    server = ManagedServer(
        UUID("00000000-0000-0000-0000-000000000301"),
        "fwq10",
        "fwq10",
        True,
        ServerCapacity(cpu_cores=64, memory_gb=256.0, gpu_count=4),
        NOW,
        NOW,
    )
    task_request = TaskRequest(
        UUID("00000000-0000-0000-0000-000000000401"),
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
        note="bring cables",
        status=TaskRequestStatus.SUBMITTED,
        created_at=NOW,
        updated_at=NOW,
    )
    cancelled_at = NOW + timedelta(hours=1)
    planned_reservation = Reservation(
        UUID("00000000-0000-0000-0000-000000000501"),
        request_id=task_request.id,
        owner_id=user.id,
        server_id=server.id,
        title="Poplar assembly",
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
    cancelled_reservation = Reservation(
        UUID("00000000-0000-0000-0000-000000000502"),
        request_id=None,
        owner_id=user.id,
        server_id=server.id,
        title="Cancelled job",
        start_at=START + timedelta(hours=4),
        end_at=START + timedelta(hours=6),
        cpu_cores=4,
        memory_gb=8.0,
        gpu_count=1,
        gpu_ids=(2,),
        status=ReservationStatus.CANCELLED,
        source=ReservationSource.ADMIN,
        created_at=NOW,
        updated_at=cancelled_at,
    )
    draft_request = TaskRequest(
        UUID("00000000-0000-0000-0000-000000000402"),
        requester_id=user.id,
        title="Draft request",
        project=None,
        preferred_server_id=server.id,
        planned_start=START + timedelta(hours=8),
        planned_duration_minutes=60,
        requested_cpu_cores=1,
        requested_memory_gb=None,
        requested_gpu_count=0,
        preferred_gpu_ids=None,
        note=None,
        status=TaskRequestStatus.DRAFT,
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
        requests.add(draft_request)
        session.commit()
        reservations.add(planned_reservation)
        reservations.add(cancelled_reservation)
        session.commit()

    upgrade_database(database_url)

    expected_planned = PlanEntry(
        planned_reservation.id,
        owner_id=user.id,
        server_id=server.id,
        title="Poplar assembly",
        project="Populus",
        start_at=planned_reservation.start_at,
        end_at=planned_reservation.end_at,
        cpu_cores=32,
        memory_gb=128.0,
        gpu_count=2,
        gpu_ids=(0, 1),
        note="bring cables",
        cancelled_at=None,
        created_at=NOW,
        updated_at=NOW,
    )
    expected_cancelled = PlanEntry(
        cancelled_reservation.id,
        owner_id=user.id,
        server_id=server.id,
        title="Cancelled job",
        project=None,
        start_at=cancelled_reservation.start_at,
        end_at=cancelled_reservation.end_at,
        cpu_cores=4,
        memory_gb=8.0,
        gpu_count=1,
        gpu_ids=(2,),
        note=None,
        cancelled_at=cancelled_at,
        created_at=NOW,
        updated_at=cancelled_at,
    )

    with session_factory() as session:
        plans = PlanRepository(session)
        assert plans.get(planned_reservation.id) == expected_planned
        assert plans.get(cancelled_reservation.id) == expected_cancelled
        assert plans.list(include_cancelled=True) == [expected_planned, expected_cancelled]

    engine = create_engine(database_url)
    with engine.begin() as connection:
        count = connection.exec_driver_sql("SELECT COUNT(*) FROM plan_entries").scalar()
    assert count == 2


def test_repositories_round_trip_domain_entities(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'roundtrip.sqlite'}"
    upgrade_database(database_url)
    _, session_factory = create_engine_and_session_factory(database_url)

    user = User(
        UUID("00000000-0000-0000-0000-000000000201"),
        "alice",
        "Alice",
        UserRole.MEMBER,
        True,
        NOW,
        NOW,
    )
    server = ManagedServer(
        UUID("00000000-0000-0000-0000-000000000301"),
        "fwq10",
        "fwq10",
        True,
        ServerCapacity(cpu_cores=64, memory_gb=256.0, gpu_count=4),
        NOW,
        NOW,
    )
    plan_entry = PlanEntry(
        UUID("00000000-0000-0000-0000-000000000701"),
        owner_id=user.id,
        server_id=server.id,
        title="Poplar assembly",
        project="Populus",
        start_at=START,
        end_at=START + timedelta(hours=2),
        cpu_cores=32,
        memory_gb=128.0,
        gpu_count=2,
        gpu_ids=(0, 1),
        note="bring cables",
        cancelled_at=None,
        created_at=NOW,
        updated_at=NOW,
    )

    with session_factory() as session:
        UserRepository(session).add(user)
        ServerRepository(session).add(server)
        session.commit()
        PlanRepository(session).add(plan_entry)
        session.commit()

    with session_factory() as session:
        assert UserRepository(session).get(user.id) == user
        assert ServerRepository(session).get_by_key("fwq10") == server
        assert PlanRepository(session).get(plan_entry.id) == plan_entry


def test_plan_window_query_uses_half_open_overlap(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'window.sqlite'}"
    upgrade_database(database_url)
    _, session_factory = create_engine_and_session_factory(database_url)

    user_id = UUID("00000000-0000-0000-0000-000000000201")
    server_id = UUID("00000000-0000-0000-0000-000000000301")
    cancelled_id = UUID("00000000-0000-0000-0000-000000000702")

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
        repo = PlanRepository(session)

        def plan_entry(title: str, start: datetime, end: datetime) -> PlanEntry:
            return PlanEntry(
                uuid4(),
                owner_id=user_id,
                server_id=server_id,
                title=title,
                project=None,
                start_at=start,
                end_at=end,
                cpu_cores=4,
                memory_gb=8.0,
                gpu_count=1,
                gpu_ids=(0,),
                note=None,
                cancelled_at=None,
                created_at=NOW,
                updated_at=NOW,
            )

        repo.add(plan_entry("first", START, START + timedelta(hours=1)))
        repo.add(plan_entry("second", START + timedelta(hours=2), START + timedelta(hours=3)))
        repo.add(plan_entry("other-day", START + timedelta(days=2), START + timedelta(days=3)))
        repo.add(
            PlanEntry(
                cancelled_id,
                owner_id=user_id,
                server_id=server_id,
                title="cancelled",
                project=None,
                start_at=START,
                end_at=START + timedelta(hours=1),
                cpu_cores=4,
                memory_gb=8.0,
                gpu_count=1,
                gpu_ids=(0,),
                note=None,
                cancelled_at=NOW,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.commit()

        window_start = START + timedelta(minutes=30)
        window_end = START + timedelta(hours=2, minutes=30)

        window_titles = [
            plan.title
            for plan in repo.list(server_id=server_id, start=window_start, end=window_end)
        ]
        assert window_titles == ["first", "second"]
        assert repo.list(
            server_id=server_id,
            start=START + timedelta(hours=3),
            end=START + timedelta(hours=4),
        ) == []
        assert all(plan.cancelled_at is None for plan in repo.list(server_id=server_id))
        cancelled_plans = repo.list(server_id=server_id, include_cancelled=True)
        assert cancelled_id in {plan.id for plan in cancelled_plans}


def test_plan_repository_filters_by_owner_and_updates(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'filters.sqlite'}"
    upgrade_database(database_url)
    _, session_factory = create_engine_and_session_factory(database_url)

    alice_id = UUID("00000000-0000-0000-0000-000000000201")
    bob_id = UUID("00000000-0000-0000-0000-000000000202")
    server_id = UUID("00000000-0000-0000-0000-000000000301")

    with session_factory() as session:
        users = UserRepository(session)
        users.add(User(alice_id, "alice", "Alice", UserRole.MEMBER, True, NOW, NOW))
        users.add(User(bob_id, "bob", "Bob", UserRole.MEMBER, True, NOW, NOW))
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
        repo = PlanRepository(session)
        repo.add(
            PlanEntry(
                UUID("00000000-0000-0000-0000-000000000701"),
                owner_id=alice_id,
                server_id=server_id,
                title="alice plan",
                project=None,
                start_at=START,
                end_at=START + timedelta(hours=1),
                cpu_cores=None,
                memory_gb=None,
                gpu_count=None,
                gpu_ids=None,
                note=None,
                cancelled_at=None,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        repo.add(
            PlanEntry(
                UUID("00000000-0000-0000-0000-000000000703"),
                owner_id=bob_id,
                server_id=server_id,
                title="bob plan",
                project=None,
                start_at=START,
                end_at=START + timedelta(hours=1),
                cpu_cores=None,
                memory_gb=None,
                gpu_count=None,
                gpu_ids=None,
                note=None,
                cancelled_at=None,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.commit()

        assert [plan.owner_id for plan in repo.list(owner_id=alice_id)] == [alice_id]

        updated = PlanEntry(
            UUID("00000000-0000-0000-0000-000000000701"),
            owner_id=alice_id,
            server_id=server_id,
            title="alice plan renamed",
            project="Populus",
            start_at=START + timedelta(hours=1),
            end_at=START + timedelta(hours=2),
            cpu_cores=8,
            memory_gb=16.0,
            gpu_count=1,
            gpu_ids=(3,),
            note="moved",
            cancelled_at=None,
            created_at=NOW,
            updated_at=NOW + timedelta(minutes=5),
        )
        repo.save(updated)
        session.commit()

    with session_factory() as session:
        stored = PlanRepository(session).get(updated.id)
        assert stored == updated


def test_unit_of_work_rolls_back_on_exception(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rollback.sqlite'}"
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
        raise RuntimeError

    with session_factory() as session:
        assert UserRepository(session).get(user.id) is None


def test_unit_of_work_commit_persists_changes(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'commit.sqlite'}"
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
