from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from labserver_contracts.common import (
    ReservationSource,
    ReservationStatus,
    TaskRequestStatus,
    UserRole,
)
from labserver_core.application.actors import CurrentActor
from labserver_core.application.request_service import RequestService
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
from sqlalchemy.exc import IntegrityError

CORE_DIR = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 9, 15, 8, 0, tzinfo=UTC)
START = datetime(2026, 9, 20, 8, 0, tzinfo=UTC)
ADMIN_ID = UUID("00000000-0000-0000-0000-000000000911")
MEMBER_ID = UUID("00000000-0000-0000-0000-000000000912")
SERVER_ID = UUID("00000000-0000-0000-0000-000000000913")
REQUEST_ID = UUID("00000000-0000-0000-0000-000000000914")
EXISTING_RESERVATION_ID = UUID("00000000-0000-0000-0000-000000000915")
NEW_RESERVATION_ID = UUID("00000000-0000-0000-0000-000000000916")
AUDIT_ID = UUID("00000000-0000-0000-0000-000000000917")


def upgrade_database(database_url: str) -> None:
    config = Config(str(CORE_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


def test_failed_reservation_insert_rolls_back_request_approval(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'approval-rollback.sqlite'}"
    upgrade_database(database_url)
    _, session_factory = create_engine_and_session_factory(database_url)

    admin = User(ADMIN_ID, "admin", "Admin", UserRole.ADMIN, True, NOW, NOW)
    member = User(MEMBER_ID, "member", "Member", UserRole.MEMBER, True, NOW, NOW)
    managed_server = ManagedServer(
        SERVER_ID,
        "fwq10",
        "fwq10",
        True,
        ServerCapacity(64, 256.0, 4),
        NOW,
        NOW,
    )
    submitted = TaskRequest(
        REQUEST_ID,
        MEMBER_ID,
        "Poplar assembly",
        None,
        SERVER_ID,
        START,
        120,
        32,
        128.0,
        2,
        (0, 1),
        None,
        TaskRequestStatus.SUBMITTED,
        NOW,
        NOW,
    )
    corrupt_existing_reservation = Reservation(
        EXISTING_RESERVATION_ID,
        REQUEST_ID,
        MEMBER_ID,
        SERVER_ID,
        "Pre-existing reservation",
        START,
        START + timedelta(minutes=120),
        1,
        None,
        0,
        None,
        ReservationStatus.PLANNED,
        ReservationSource.REQUEST,
        NOW,
        NOW,
    )

    with session_factory() as session:
        UserRepository(session).add(admin)
        UserRepository(session).add(member)
        ServerRepository(session).add(managed_server)
        session.commit()
        RequestRepository(session).add(submitted)
        session.commit()
        ReservationRepository(session).add(corrupt_existing_reservation)
        session.commit()

    service = RequestService(
        lambda: SqlAlchemyUnitOfWork(session_factory),
        clock=lambda: NOW,
        reservation_id_factory=lambda: NEW_RESERVATION_ID,
        audit_id_factory=lambda: AUDIT_ID,
    )

    with pytest.raises(IntegrityError):
        service.approve_request(CurrentActor(ADMIN_ID, UserRole.ADMIN), REQUEST_ID)

    with session_factory() as session:
        persisted = RequestRepository(session).get(REQUEST_ID)
        assert persisted is not None
        assert persisted.status is TaskRequestStatus.SUBMITTED
        assert persisted.status_changed_by is None
        reservations = ReservationRepository(session).list_for_server(
            SERVER_ID,
            START,
            START + timedelta(minutes=120),
        )
        assert [item.id for item in reservations] == [EXISTING_RESERVATION_ID]
