from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from labserver_contracts.reservations import ReservationRead

from labserver_core.api.dependencies import get_current_actor, get_reservation_service
from labserver_core.application.actors import CurrentActor
from labserver_core.application.reservation_service import ReservationService
from labserver_core.domain.errors import DomainValidationError

router = APIRouter(prefix="/reservations", tags=["reservations"])


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DomainValidationError("Reservation query timestamps must include a timezone")
    return value.astimezone(UTC)


@router.get("", response_model=list[ReservationRead])
def list_reservations(
    start: datetime,
    end: datetime,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    service: Annotated[ReservationService, Depends(get_reservation_service)],
    server_id: UUID | None = None,
) -> list[ReservationRead]:
    items = service.list_reservations(
        actor,
        start=_utc(start),
        end=_utc(end),
        server_id=server_id,
    )
    return [ReservationRead.model_validate(item) for item in items]
