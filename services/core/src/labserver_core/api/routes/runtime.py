from typing import Annotated

from fastapi import APIRouter, Depends
from labserver_contracts.runtime import (
    HostRuntimeRead,
    HostRuntimeReport,
    RuntimeOverviewRead,
)

from labserver_core.api.dependencies import (
    get_current_actor,
    get_runtime_service,
    verify_collector_token,
)
from labserver_core.application.actors import CurrentActor
from labserver_core.application.runtime_service import RuntimeService

router = APIRouter(prefix="/runtime", tags=["runtime"])


@router.post("/report")
def submit_runtime_report(
    report: HostRuntimeReport,
    _: Annotated[None, Depends(verify_collector_token)],
    service: Annotated[RuntimeService, Depends(get_runtime_service)],
) -> dict[str, str]:
    service.submit_report(report)
    return {"status": "ok"}


@router.get("/overview", response_model=RuntimeOverviewRead)
def get_runtime_overview(
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    service: Annotated[RuntimeService, Depends(get_runtime_service)],
) -> RuntimeOverviewRead:
    return service.get_overview(actor)


@router.get("/servers/{server_key}", response_model=HostRuntimeRead)
def get_server_runtime(
    server_key: str,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    service: Annotated[RuntimeService, Depends(get_runtime_service)],
) -> HostRuntimeRead:
    return service.get_server_runtime(server_key, actor)
