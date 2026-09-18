from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient
from labserver_contracts.monitoring import FreshnessStatus
from labserver_contracts.plans import PlanDisplayState, PlanRead
from labserver_contracts.runtime import (
    GpuDeviceRuntime,
    GpuProcessInfo,
    HostRuntimeRead,
    RuntimeOverviewRead,
    RuntimePlanCorrelation,
    RuntimeStatus,
)
from labserver_web.clients.core import CoreClientError

from .conftest import FakeCoreClient


def test_anonymous_running_is_401(anonymous_client: TestClient) -> None:
    response = anonymous_client.get("/running")
    assert response.status_code == 401


def test_authenticated_member_sees_running_overview(
    client: TestClient, fake_core: FakeCoreClient
) -> None:
    now = datetime.now(UTC)
    plan_id = UUID("00000000-0000-0000-0000-000000000001")
    owner_id = UUID("00000000-0000-0000-0000-000000000002")

    matched_proc = GpuProcessInfo(
        gpu_id=0,
        pid=12345,
        process_name="python train.py",
        username="alice",
        used_memory_mb=8192.0,
        correlation=RuntimePlanCorrelation.MATCHED,
        matched_plan_id=plan_id,
        matched_plan_title="RNA-seq assembly",
        matched_plan_owner="alice",
    )

    unplanned_proc = GpuProcessInfo(
        gpu_id=1,
        pid=54321,
        process_name="/usr/bin/python3 rogue.py",
        username="charlie",
        used_memory_mb=4096.0,
        correlation=RuntimePlanCorrelation.UNPLANNED,
    )

    gpu0 = GpuDeviceRuntime(
        index=0,
        name="NVIDIA A100-SXM4-40GB",
        memory_total_mb=40960.0,
        memory_used_mb=8192.0,
        utilization_gpu_percent=75.0,
        temperature_celsius=52,
        processes=[matched_proc],
        active_plans_count=1,
    )

    gpu1 = GpuDeviceRuntime(
        index=1,
        name="NVIDIA A100-SXM4-40GB",
        memory_total_mb=40960.0,
        memory_used_mb=4096.0,
        utilization_gpu_percent=20.0,
        temperature_celsius=45,
        processes=[unplanned_proc],
        active_plans_count=0,
    )

    ongoing_plan = PlanRead(
        id=plan_id,
        owner_id=owner_id,
        server_id=UUID("00000000-0000-0000-0000-000000002001"),
        title="RNA-seq assembly",
        project="Poplar",
        start_at=now,
        end_at=now,
        cpu_cores=16,
        memory_gb=64.0,
        gpu_count=1,
        gpu_ids=(0,),
        note=None,
        cancelled_at=None,
        created_at=now,
        updated_at=now,
        display_state=PlanDisplayState.ONGOING,
    )

    host_runtime = HostRuntimeRead(
        server_key="fwq57",
        display_name="fwq57",
        status=RuntimeStatus.ACTIVE,
        reported_at=now,
        freshness=FreshnessStatus.FRESH,
        gpus=[gpu0, gpu1],
        ongoing_plans=[ongoing_plan],
        unplanned_processes_count=1,
    )

    fake_core.runtime_overview = RuntimeOverviewRead(
        servers=[host_runtime],
        observed_at=now,
    )

    response = client.get("/running")
    assert response.status_code == 200
    body = response.text

    assert "Running Compute" in body
    assert "fwq57" in body
    assert "● Active" in body
    assert "1 unplanned" in body
    assert "NVIDIA A100-SXM4-40GB" in body
    assert "12345" in body
    assert "alice" in body
    assert "● Matched" in body
    assert "RNA-seq assembly" in body
    assert "54321" in body
    assert "charlie" in body
    assert "▲ Unplanned" in body
    assert "/schedule?server=fwq57" in body


def test_running_core_failure_renders_error(
    client: TestClient, fake_core: FakeCoreClient
) -> None:
    fake_core.error = CoreClientError(503, "service_unavailable", "Core collector backend unavailable")
    response = client.get("/running")
    assert response.status_code == 503
    assert "Core collector backend unavailable" in response.text


def test_empty_running_overview(
    client: TestClient, fake_core: FakeCoreClient
) -> None:
    fake_core.runtime_overview = RuntimeOverviewRead(
        servers=[],
        observed_at=datetime.now(UTC),
    )
    response = client.get("/running")
    assert response.status_code == 200
    assert "No managed servers registered or reporting runtime status" in response.text
