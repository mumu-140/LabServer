from datetime import datetime
from uuid import UUID

from labserver_core.domain.entities import Reservation
from labserver_core.domain.errors import DomainValidationError

from .actors import CurrentActor, require_active_actor
from .ports import UnitOfWorkFactory


class ReservationService:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def list_reservations(
        self,
        actor: CurrentActor,
        *,
        start: datetime,
        end: datetime,
        server_id: UUID | None = None,
    ) -> list[Reservation]:
        if start >= end:
            raise DomainValidationError("Reservation query start must be before end")
        with self._uow_factory() as uow:
            require_active_actor(actor, uow.users.get(actor.user_id))
            if server_id is not None:
                return uow.reservations.list_for_server(server_id, start, end)
            return uow.reservations.list_window(start, end)
