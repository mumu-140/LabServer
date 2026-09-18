from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from labserver_contracts.monitoring import (
    DashboardRead,
    HostMetricsRead,
    ServerDashboardCard,
)
from labserver_contracts.plans import PlanDisplayState, PlanRead
from labserver_contracts.servers import ServerRead

from labserver_core.adapters.monitoring import HostMetricsProvider
from labserver_core.domain.entities import plan_display_state
from labserver_core.domain.errors import NotFound

from .actors import CurrentActor, require_active_actor
from .ports import UnitOfWorkFactory


def _utc_now() -> datetime:
    return datetime.now(UTC)


class MonitoringService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        metrics_provider: HostMetricsProvider,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._uow_factory = uow_factory
        self._metrics_provider = metrics_provider
        self._clock = clock

    async def get_dashboard(self, actor: CurrentActor) -> DashboardRead:
        now = self._clock()
        with self._uow_factory() as uow:
            require_active_actor(actor, uow.users.get(actor.user_id))
            servers = uow.servers.list_all()

            enabled_servers = [s for s in servers if s.enabled]
            capacities = {
                s.key: (s.capacity.memory_gb, s.capacity.cpu_cores) for s in enabled_servers
            }

            metrics_map = await self._metrics_provider.get_metrics(
                [s.key for s in enabled_servers],
                capacities,
            )

            window_start = now - timedelta(hours=2)
            window_end = now + timedelta(hours=24)

            cards: list[ServerDashboardCard] = []
            for server in enabled_servers:
                server_read = ServerRead(
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
                metrics = metrics_map.get(server.key)

                raw_plans = uow.plans.list(
                    server_id=server.id,
                    start=window_start,
                    end=window_end,
                    include_cancelled=False,
                )

                near_term: list[PlanRead] = []
                active_count = 0
                for p in raw_plans:
                    state = plan_display_state(p, now)
                    if state in (PlanDisplayState.ONGOING, PlanDisplayState.UPCOMING):
                        pread = PlanRead(
                            id=p.id,
                            owner_id=p.owner_id,
                            server_id=p.server_id,
                            title=p.title,
                            project=p.project,
                            start_at=p.start_at,
                            end_at=p.end_at,
                            cpu_cores=p.cpu_cores,
                            memory_gb=p.memory_gb,
                            gpu_count=p.gpu_count,
                            gpu_ids=p.gpu_ids,
                            note=p.note,
                            cancelled_at=p.cancelled_at,
                            created_at=p.created_at,
                            updated_at=p.updated_at,
                            display_state=state,
                        )
                        near_term.append(pread)
                        if state == PlanDisplayState.ONGOING:
                            active_count += 1

                cards.append(
                    ServerDashboardCard(
                        server=server_read,
                        metrics=metrics,
                        active_plans_count=active_count,
                        near_term_plans=near_term[:5],
                    )
                )

            return DashboardRead(cards=cards, observed_at=now)

    async def get_server_metrics(self, actor: CurrentActor, server_key: str) -> HostMetricsRead:
        with self._uow_factory() as uow:
            require_active_actor(actor, uow.users.get(actor.user_id))
            server = uow.servers.get_by_key(server_key)
            if server is None:
                raise NotFound(f"Server with key {server_key!r} does not exist")

            return await self._metrics_provider.get_server_metrics(
                server_key,
                memory_gb=server.capacity.memory_gb,
                cpu_cores=server.capacity.cpu_cores,
            )
