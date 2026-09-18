from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from labserver_contracts.monitoring import FreshnessStatus
from labserver_contracts.plans import PlanDisplayState, PlanRead
from labserver_contracts.runtime import (
    GpuDeviceRuntime,
    GpuProcessInfo,
    HostRuntimeRead,
    HostRuntimeReport,
    RuntimeOverviewRead,
    RuntimePlanCorrelation,
    RuntimeStatus,
)

from labserver_core.domain.entities import ManagedServer, PlanEntry, plan_display_state
from labserver_core.domain.errors import NotFound
from labserver_core.persistence.unit_of_work import SqlAlchemyUnitOfWork

from .actors import CurrentActor, require_active_actor
from .ports import UnitOfWorkFactory
from .runtime_store import RuntimeStore


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _plan_to_read(plan: PlanEntry, now: datetime) -> PlanRead:
    return PlanRead(
        id=plan.id,
        owner_id=plan.owner_id,
        server_id=plan.server_id,
        title=plan.title,
        project=plan.project,
        start_at=plan.start_at,
        end_at=plan.end_at,
        cpu_cores=plan.cpu_cores,
        memory_gb=plan.memory_gb,
        gpu_count=plan.gpu_count,
        gpu_ids=plan.gpu_ids,
        note=plan.note,
        cancelled_at=plan.cancelled_at,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
        display_state=plan_display_state(plan, now),
    )


class RuntimeService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        runtime_store: RuntimeStore,
        *,
        clock: Callable[[], datetime] = _utc_now,
        freshness_threshold_seconds: float = 120.0,
    ) -> None:
        self._uow_factory = uow_factory
        self._runtime_store = runtime_store
        self._clock = clock
        self._freshness_threshold_seconds = freshness_threshold_seconds

    def submit_report(self, report: HostRuntimeReport) -> None:
        with self._uow_factory() as uow:
            server = uow.servers.get_by_key(report.server_key)
            if server is None:
                raise NotFound(f"Server with key {report.server_key!r} does not exist")
        self._runtime_store.set_report(report)

    def get_server_runtime(self, server_key: str, actor: CurrentActor) -> HostRuntimeRead:
        with self._uow_factory() as uow:
            require_active_actor(actor, uow.users.get(actor.user_id))
            server = uow.servers.get_by_key(server_key)
            if server is None:
                raise NotFound(f"Server with key {server_key!r} does not exist")
            users_map = {u.id: u.username for u in uow.users.list_all()}
            return self._build_host_runtime(server, users_map, uow)

    def get_overview(self, actor: CurrentActor) -> RuntimeOverviewRead:
        now = self._clock()
        with self._uow_factory() as uow:
            require_active_actor(actor, uow.users.get(actor.user_id))
            servers = uow.servers.list_all()
            users_map = {u.id: u.username for u in uow.users.list_all()}
            reads = [
                self._build_host_runtime(s, users_map, uow)
                for s in servers
                if s.enabled
            ]
            return RuntimeOverviewRead(servers=reads, observed_at=now)

    def _build_host_runtime(
        self,
        server: ManagedServer,
        users_map: dict[UUID, str],
        uow: SqlAlchemyUnitOfWork | object,
    ) -> HostRuntimeRead:
        now = self._clock()
        report = self._runtime_store.get_report(server.key)
        freshness = self._runtime_store.get_freshness(
            server.key, now, self._freshness_threshold_seconds
        )

        plans_repo = getattr(uow, "plans")
        plans = plans_repo.list(
            server_id=server.id,
            start=now,
            end=now,
            include_cancelled=False,
        )
        ongoing_plans = [
            p for p in plans if plan_display_state(p, now) == PlanDisplayState.ONGOING
        ]
        ongoing_reads = [_plan_to_read(p, now) for p in ongoing_plans]

        if report is None:
            return HostRuntimeRead(
                server_key=server.key,
                display_name=server.display_name,
                status=RuntimeStatus.UNAVAILABLE,
                reported_at=None,
                freshness=freshness,
                gpus=[],
                ongoing_plans=ongoing_reads,
                unplanned_processes_count=0,
            )

        correlated_gpus: list[GpuDeviceRuntime] = []
        total_unplanned = 0
        has_active_processes = False

        for gpu in report.gpus:
            gpu_plans = [
                p for p in ongoing_plans
                if p.gpu_ids is None or gpu.index in p.gpu_ids
            ]
            correlated_procs: list[GpuProcessInfo] = []
            for proc in gpu.processes:
                has_active_processes = True
                matched_plan: tuple[PlanEntry, str] | None = None
                for plan in gpu_plans:
                    owner_username = users_map.get(plan.owner_id)
                    if owner_username and owner_username.lower() == proc.username.lower():
                        matched_plan = (plan, owner_username)
                        break

                if matched_plan is not None:
                    p, owner_uname = matched_plan
                    correlated_procs.append(
                        GpuProcessInfo(
                            gpu_id=proc.gpu_id,
                            pid=proc.pid,
                            process_name=proc.process_name,
                            username=proc.username,
                            used_memory_mb=proc.used_memory_mb,
                            correlation=RuntimePlanCorrelation.MATCHED,
                            matched_plan_id=p.id,
                            matched_plan_title=p.title,
                            matched_plan_owner=owner_uname,
                        )
                    )
                else:
                    total_unplanned += 1
                    correlated_procs.append(
                        GpuProcessInfo(
                            gpu_id=proc.gpu_id,
                            pid=proc.pid,
                            process_name=proc.process_name,
                            username=proc.username,
                            used_memory_mb=proc.used_memory_mb,
                            correlation=RuntimePlanCorrelation.UNPLANNED,
                        )
                    )

            correlated_gpus.append(
                GpuDeviceRuntime(
                    index=gpu.index,
                    name=gpu.name,
                    memory_total_mb=gpu.memory_total_mb,
                    memory_used_mb=gpu.memory_used_mb,
                    utilization_gpu_percent=gpu.utilization_gpu_percent,
                    temperature_celsius=gpu.temperature_celsius,
                    processes=correlated_procs,
                    active_plans_count=len(gpu_plans),
                )
            )

        if freshness in (FreshnessStatus.STALE, FreshnessStatus.UNKNOWN):
            status = RuntimeStatus.UNAVAILABLE
        elif has_active_processes:
            status = RuntimeStatus.ACTIVE
        else:
            status = RuntimeStatus.IDLE

        return HostRuntimeRead(
            server_key=server.key,
            display_name=server.display_name,
            status=status,
            reported_at=report.reported_at,
            freshness=freshness,
            gpus=correlated_gpus,
            ongoing_plans=ongoing_reads,
            unplanned_processes_count=total_unplanned,
        )
