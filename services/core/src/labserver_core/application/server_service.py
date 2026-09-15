from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from labserver_contracts.servers import ServerCreate, ServerUpdate

from labserver_core.domain.entities import ManagedServer, ServerCapacity
from labserver_core.domain.errors import DomainValidationError, NotFound

from .actors import CurrentActor, require_active_actor, require_admin
from .ports import UnitOfWorkFactory


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ServerService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        *,
        clock: Callable[[], datetime] = _utc_now,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._id_factory = id_factory

    def list_servers(self, actor: CurrentActor) -> list[ManagedServer]:
        with self._uow_factory() as uow:
            require_active_actor(actor, uow.users.get(actor.user_id))
            return uow.servers.list_all()

    def create_server(self, actor: CurrentActor, data: ServerCreate) -> ManagedServer:
        with self._uow_factory() as uow:
            require_active_actor(actor, uow.users.get(actor.user_id))
            require_admin(actor)
            if uow.servers.get_by_key(data.key) is not None:
                raise DomainValidationError(f"Server key {data.key!r} already exists")

            now = self._clock()
            server = ManagedServer(
                id=self._id_factory(),
                key=data.key,
                display_name=data.display_name,
                enabled=data.enabled,
                capacity=ServerCapacity(data.cpu_cores, data.memory_gb, data.gpu_count),
                created_at=now,
                updated_at=now,
            )
            uow.servers.add(server)
            uow.commit()
            return server

    def update_server(
        self,
        actor: CurrentActor,
        server_id: UUID,
        data: ServerUpdate,
    ) -> ManagedServer:
        with self._uow_factory() as uow:
            require_active_actor(actor, uow.users.get(actor.user_id))
            require_admin(actor)
            current = uow.servers.get(server_id)
            if current is None:
                raise NotFound(f"Server {server_id} was not found")

            fields = data.model_fields_set
            capacity = ServerCapacity(
                cpu_cores=(
                    data.cpu_cores if "cpu_cores" in fields else current.capacity.cpu_cores
                ),
                memory_gb=(
                    data.memory_gb if "memory_gb" in fields else current.capacity.memory_gb
                ),
                gpu_count=(
                    data.gpu_count if "gpu_count" in fields else current.capacity.gpu_count
                ),
            )
            updated = replace(
                current,
                display_name=(
                    data.display_name
                    if "display_name" in fields and data.display_name is not None
                    else current.display_name
                ),
                enabled=(
                    data.enabled
                    if "enabled" in fields and data.enabled is not None
                    else current.enabled
                ),
                capacity=capacity,
                updated_at=self._clock(),
            )
            uow.servers.save(updated)
            uow.commit()
            return updated
