from types import TracebackType

from sqlalchemy.orm import Session

from .database import SessionFactory
from .repositories import (
    AuditRepository,
    PlanRepository,
    RequestRepository,
    ReservationRepository,
    ServerRepository,
    UserRepository,
)


class SqlAlchemyUnitOfWork:
    session: Session
    users: UserRepository
    servers: ServerRepository
    requests: RequestRepository
    reservations: ReservationRepository
    plans: PlanRepository
    audits: AuditRepository

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def __enter__(self) -> "SqlAlchemyUnitOfWork":
        self.session = self._session_factory()
        self.users = UserRepository(self.session)
        self.servers = ServerRepository(self.session)
        self.requests = RequestRepository(self.session)
        self.reservations = ReservationRepository(self.session)
        self.plans = PlanRepository(self.session)
        self.audits = AuditRepository(self.session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            self.rollback()
        self.session.close()

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
