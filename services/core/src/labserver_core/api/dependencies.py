from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from labserver_core.application.actors import CurrentActor
from labserver_core.application.plan_service import PlanService
from labserver_core.application.ports import UnitOfWork, UnitOfWorkFactory
from labserver_core.application.request_service import RequestService
from labserver_core.application.reservation_service import ReservationService
from labserver_core.application.server_service import ServerService
from labserver_core.application.user_service import UserService


def get_current_actor() -> CurrentActor:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication adapter is not configured",
    )


def get_uow_factory(request: Request) -> UnitOfWorkFactory:
    factory: Callable[[], UnitOfWork] = request.app.state.uow_factory
    return factory


def get_user_service(
    uow_factory: Annotated[UnitOfWorkFactory, Depends(get_uow_factory)],
) -> UserService:
    return UserService(uow_factory)


def get_server_service(
    uow_factory: Annotated[UnitOfWorkFactory, Depends(get_uow_factory)],
) -> ServerService:
    return ServerService(uow_factory)


def get_request_service(
    uow_factory: Annotated[UnitOfWorkFactory, Depends(get_uow_factory)],
) -> RequestService:
    return RequestService(uow_factory)


def get_plan_service(
    uow_factory: Annotated[UnitOfWorkFactory, Depends(get_uow_factory)],
) -> PlanService:
    return PlanService(uow_factory)


def get_reservation_service(
    uow_factory: Annotated[UnitOfWorkFactory, Depends(get_uow_factory)],
) -> ReservationService:
    return ReservationService(uow_factory)


def require_database_ready(request: Request) -> None:
    try:
        with request.app.state.engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        ) from exc
