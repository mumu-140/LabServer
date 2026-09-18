from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from labserver_contracts.common import UserRole
from labserver_contracts.monitoring import FreshnessStatus
from labserver_contracts.runtime import (
    GpuDeviceRuntime,
    GpuProcessInfo,
    HostRuntimeReport,
    RuntimePlanCorrelation,
    RuntimeStatus,
)
from labserver_core.application.actors import CurrentActor
from labserver_core.application.runtime_service import RuntimeService
from labserver_core.application.runtime_store import RuntimeStore
from labserver_core.domain.entities import ManagedServer, PlanEntry, ServerCapacity, User
from labserver_core.domain.errors import Forbidden, NotFound
from labserver_core.persistence.database import create_engine_and_session_factory
from labserver_core.persistence.unit_of_work import SqlAlchemyUnitOfWork

CORE_DIR = Path(__file__).resolve().parents[2]


def upgrade_database(database_url: str, revision: str = "head") -> None:
    config = Config(str(CORE_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    config.set_main_option("sqlalchemy.isolation_level", "AUTOCOMMIT")
    command.upgrade(config, revision)


def _make_db(tmp_path: Path):
    db_file = tmp_path / "runtime_test.sqlite"
    database_url = f"sqlite:///{db_file}"
    upgrade_database(database_url)
    _, session_factory = create_engine_and_session_factory(database_url)

    def uow_factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    return uow_factory


def test_runtime_store_freshness() -> None:
    store = RuntimeStore()
    now = datetime(2026, 9, 18, 12, 0, 0, tzinfo=UTC)

    assert store.get_freshness("fwq57", now) == FreshnessStatus.UNKNOWN

    report = HostRuntimeReport(
        server_key="fwq57",
        reported_at=now,
        gpus=[],
    )
    store.set_report(report)
    assert store.get_report("fwq57") == report
    assert store.get_freshness("fwq57", now, threshold_seconds=60.0) == FreshnessStatus.FRESH
    assert (
        store.get_freshness("fwq57", now + timedelta(seconds=70), threshold_seconds=60.0)
        == FreshnessStatus.STALE
    )


def test_submit_report_unknown_server_raises_not_found(tmp_path: Path) -> None:
    uow_factory = _make_db(tmp_path)
    store = RuntimeStore()
    service = RuntimeService(uow_factory, store)

    now = datetime.now(UTC)
    report = HostRuntimeReport(
        server_key="nonexistent",
        reported_at=now,
        gpus=[],
    )
    with pytest.raises(NotFound):
        service.submit_report(report)


def test_runtime_correlation_matches_plan_and_detects_unplanned(tmp_path: Path) -> None:
    uow_factory = _make_db(tmp_path)
    store = RuntimeStore()
    now = datetime(2026, 9, 18, 12, 0, 0, tzinfo=UTC)
    service = RuntimeService(uow_factory, store, clock=lambda: now)

    user_id = uuid4()
    server_id = uuid4()
    plan_id = uuid4()

    with uow_factory() as uow:
        # Seed user
        uow.users.add(
            User(
                id=user_id,
                username="yangs",
                display_name="Yang S",
                role=UserRole.MEMBER,
                enabled=True,
                created_at=now,
                updated_at=now,
            )
        )
        # Seed server
        uow.servers.add(
            ManagedServer(
                id=server_id,
                key="fwq57",
                display_name="fwq57",
                enabled=True,
                capacity=ServerCapacity(cpu_cores=128, memory_gb=251.0, gpu_count=4),
                created_at=now,
                updated_at=now,
            )
        )
        # Seed active plan for yangs on GPU 0
        uow.plans.add(
            PlanEntry(
                id=plan_id,
                owner_id=user_id,
                server_id=server_id,
                title="Model Training",
                project="NLP",
                start_at=now - timedelta(hours=1),
                end_at=now + timedelta(hours=2),
                cpu_cores=16,
                memory_gb=64.0,
                gpu_count=1,
                gpu_ids=(0,),
                note=None,
                cancelled_at=None,
                created_at=now,
                updated_at=now,
            )
        )
        uow.commit()

    # Submit report
    service.submit_report(
        HostRuntimeReport(
            server_key="fwq57",
            reported_at=now,
            gpus=[
                GpuDeviceRuntime(
                    index=0,
                    name="NVIDIA A100",
                    memory_total_mb=40960.0,
                    memory_used_mb=12000.0,
                    processes=[
                        GpuProcessInfo(
                            gpu_id=0,
                            pid=1111,
                            process_name="python train.py",
                            username="yangs",
                            used_memory_mb=11500.0,
                        )
                    ],
                ),
                GpuDeviceRuntime(
                    index=1,
                    name="NVIDIA A100",
                    memory_total_mb=40960.0,
                    memory_used_mb=5000.0,
                    processes=[
                        GpuProcessInfo(
                            gpu_id=1,
                            pid=2222,
                            process_name="python test.py",
                            username="unregistered_user",
                            used_memory_mb=4500.0,
                        )
                    ],
                ),
            ],
        )
    )

    actor = CurrentActor(user_id=user_id, role=UserRole.MEMBER)
    result = service.get_server_runtime("fwq57", actor)

    assert result.server_key == "fwq57"
    assert result.status == RuntimeStatus.ACTIVE
    assert result.freshness == FreshnessStatus.FRESH
    assert len(result.gpus) == 2

    # GPU 0: matched with plan
    gpu0 = result.gpus[0]
    assert len(gpu0.processes) == 1
    p0 = gpu0.processes[0]
    assert p0.correlation == RuntimePlanCorrelation.MATCHED
    assert p0.matched_plan_id == plan_id
    assert p0.matched_plan_owner == "yangs"
    assert gpu0.active_plans_count == 1

    # GPU 1: unplanned
    gpu1 = result.gpus[1]
    assert len(gpu1.processes) == 1
    p1 = gpu1.processes[0]
    assert p1.correlation == RuntimePlanCorrelation.UNPLANNED
    assert p1.matched_plan_id is None
    assert gpu1.active_plans_count == 0

    assert result.unplanned_processes_count == 1


def test_get_overview_aggregates_servers(tmp_path: Path) -> None:
    uow_factory = _make_db(tmp_path)
    store = RuntimeStore()
    now = datetime(2026, 9, 18, 12, 0, 0, tzinfo=UTC)
    service = RuntimeService(uow_factory, store, clock=lambda: now)

    user_id = uuid4()
    with uow_factory() as uow:
        uow.users.add(
            User(
                id=user_id,
                username="admin",
                display_name="Admin",
                role=UserRole.ADMIN,
                enabled=True,
                created_at=now,
                updated_at=now,
            )
        )
        uow.servers.add(
            ManagedServer(
                id=uuid4(),
                key="fwq10",
                display_name="fwq10",
                enabled=True,
                capacity=ServerCapacity(cpu_cores=88, memory_gb=503.0, gpu_count=0),
                created_at=now,
                updated_at=now,
            )
        )
        uow.servers.add(
            ManagedServer(
                id=uuid4(),
                key="fwq51",
                display_name="fwq51",
                enabled=True,
                capacity=ServerCapacity(cpu_cores=80, memory_gb=503.0, gpu_count=1),
                created_at=now,
                updated_at=now,
            )
        )
        uow.commit()

    # Report only for fwq51
    service.submit_report(
        HostRuntimeReport(
            server_key="fwq51",
            reported_at=now,
            gpus=[],
        )
    )

    actor = CurrentActor(user_id=user_id, role=UserRole.ADMIN)
    overview = service.get_overview(actor)

    assert len(overview.servers) == 2
    by_key = {s.server_key: s for s in overview.servers}
    assert by_key["fwq10"].status == RuntimeStatus.UNAVAILABLE
    assert by_key["fwq51"].status == RuntimeStatus.IDLE


def test_disabled_actor_raises_forbidden(tmp_path: Path) -> None:
    uow_factory = _make_db(tmp_path)
    store = RuntimeStore()
    now = datetime.now(UTC)
    service = RuntimeService(uow_factory, store)

    user_id = uuid4()
    with uow_factory() as uow:
        uow.users.add(
            User(
                id=user_id,
                username="disabled_user",
                display_name="Disabled",
                role=UserRole.MEMBER,
                enabled=False,
                created_at=now,
                updated_at=now,
            )
        )
        uow.commit()

    actor = CurrentActor(user_id=user_id, role=UserRole.MEMBER)
    with pytest.raises(Forbidden):
        service.get_overview(actor)
