from typing import Annotated

from fastapi import APIRouter, Depends
from labserver_contracts.monitoring import DashboardRead, HostMetricsRead

from labserver_core.api.dependencies import (
    get_current_actor,
    get_monitoring_service,
)
from labserver_core.application.actors import CurrentActor
from labserver_core.application.monitoring_service import MonitoringService

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/dashboard", response_model=DashboardRead)
async def get_dashboard(
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    service: Annotated[MonitoringService, Depends(get_monitoring_service)],
) -> DashboardRead:
    return await service.get_dashboard(actor)


@router.get("/servers/{server_key}", response_model=HostMetricsRead)
async def get_server_metrics(
    server_key: str,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    service: Annotated[MonitoringService, Depends(get_monitoring_service)],
) -> HostMetricsRead:
    return await service.get_server_metrics(actor, server_key)
