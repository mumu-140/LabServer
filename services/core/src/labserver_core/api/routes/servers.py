from typing import Annotated

from fastapi import APIRouter, Depends, status
from labserver_contracts.servers import ServerCreate, ServerRead

from labserver_core.api.dependencies import get_current_actor, get_server_service
from labserver_core.application.actors import CurrentActor
from labserver_core.application.server_service import ServerService
from labserver_core.domain.entities import ManagedServer

router = APIRouter(prefix="/servers", tags=["servers"])


def _read(server: ManagedServer) -> ServerRead:
    return ServerRead(
        id=server.id,
        key=server.key,
        display_name=server.display_name,
        enabled=server.enabled,
        cpu_cores=server.capacity.cpu_cores,
        memory_gb=server.capacity.memory_gb,
        gpu_count=server.capacity.gpu_count,
        created_at=server.created_at,
        updated_at=server.updated_at,
    )


@router.get("", response_model=list[ServerRead])
def list_servers(
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    service: Annotated[ServerService, Depends(get_server_service)],
) -> list[ServerRead]:
    return [_read(item) for item in service.list_servers(actor)]


@router.post("", response_model=ServerRead, status_code=status.HTTP_201_CREATED)
def create_server(
    data: ServerCreate,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    service: Annotated[ServerService, Depends(get_server_service)],
) -> ServerRead:
    return _read(service.create_server(actor, data))
