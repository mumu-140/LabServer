from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from labserver_core.adapters.monitoring import HostMetricsProvider
from labserver_core.application.actors import CurrentActor
from labserver_core.application.auth_service import AuthService
from labserver_core.application.monitoring_service import MonitoringService
from labserver_core.application.plan_service import PlanService
from labserver_core.application.ports import UnitOfWork, UnitOfWorkFactory
from labserver_core.application.server_service import ServerService
from labserver_core.application.user_service import UserService


def get_uow_factory(request: Request) -> UnitOfWorkFactory:

    factory: Callable[[], UnitOfWork] = request.app.state.uow_factory
    return factory


def get_auth_service(request: Request) -> AuthService:
    service: AuthService = request.app.state.auth_service
    return service


def get_current_actor(
    request: Request,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> CurrentActor:
    token = request.cookies.get("labserver_session")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return auth_service.resolve(token)


def get_user_service(
    uow_factory: Annotated[UnitOfWorkFactory, Depends(get_uow_factory)],
) -> UserService:
    return UserService(uow_factory)


def get_server_service(
    uow_factory: Annotated[UnitOfWorkFactory, Depends(get_uow_factory)],
) -> ServerService:
    return ServerService(uow_factory)


def get_plan_service(
    uow_factory: Annotated[UnitOfWorkFactory, Depends(get_uow_factory)],
) -> PlanService:
    return PlanService(uow_factory)


def get_monitoring_service(
    request: Request,
    uow_factory: Annotated[UnitOfWorkFactory, Depends(get_uow_factory)],
) -> MonitoringService:
    metrics_provider: HostMetricsProvider = request.app.state.metrics_provider
    return MonitoringService(uow_factory, metrics_provider)



def require_database_ready(request: Request) -> None:
    try:
        with request.app.state.engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        ) from exc
