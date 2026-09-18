from datetime import UTC, datetime
from uuid import uuid4

import pytest
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
from pydantic import ValidationError


def test_runtime_enums_are_stable() -> None:
    assert [s.value for s in RuntimeStatus] == ["active", "idle", "unavailable"]
    assert [c.value for c in RuntimePlanCorrelation] == [
        "matched",
        "unplanned",
        "idle_reservation",
    ]


def test_gpu_process_info_serialization() -> None:
    plan_id = uuid4()
    process = GpuProcessInfo(
        gpu_id=0,
        pid=12345,
        process_name="/usr/bin/python3",
        username="yangs",
        used_memory_mb=4096.0,
        correlation=RuntimePlanCorrelation.MATCHED,
        matched_plan_id=plan_id,
        matched_plan_title="LLM Fine-tuning",
        matched_plan_owner="yangs",
    )
    dumped = process.model_dump(mode="json")
    assert dumped["gpu_id"] == 0
    assert dumped["pid"] == 12345
    assert dumped["username"] == "yangs"
    assert dumped["correlation"] == "matched"
    assert dumped["matched_plan_id"] == str(plan_id)


def test_gpu_device_runtime_serialization() -> None:
    device = GpuDeviceRuntime(
        index=1,
        name="NVIDIA A100-SXM4-40GB",
        memory_total_mb=40960.0,
        memory_used_mb=12000.0,
        utilization_gpu_percent=78.5,
        temperature_celsius=52,
        processes=[
            GpuProcessInfo(
                gpu_id=1,
                pid=9876,
                process_name="python train.py",
                username="alice",
                used_memory_mb=11500.0,
            )
        ],
        active_plans_count=1,
    )
    dumped = device.model_dump(mode="json")
    assert dumped["index"] == 1
    assert dumped["name"] == "NVIDIA A100-SXM4-40GB"
    assert len(dumped["processes"]) == 1
    assert dumped["processes"][0]["pid"] == 9876


def test_host_runtime_report_validation() -> None:
    now = datetime.now(UTC)
    report = HostRuntimeReport.model_validate(
        {
            "server_key": "fwq57",
            "reported_at": now.isoformat(),
            "gpus": [
                {
                    "index": 0,
                    "name": "Tesla V100",
                    "memory_total_mb": 32768.0,
                    "memory_used_mb": 0.0,
                }
            ],
        }
    )
    assert report.server_key == "fwq57"
    assert len(report.gpus) == 1
    assert report.gpus[0].name == "Tesla V100"

    # Reject naive datetime
    with pytest.raises(ValidationError):
        HostRuntimeReport.model_validate(
            {
                "server_key": "fwq57",
                "reported_at": "2026-09-18T12:00:00",
            }
        )


def test_host_runtime_read_and_overview() -> None:
    now = datetime.now(UTC)
    plan = PlanRead(
        id=uuid4(),
        server_id=uuid4(),
        owner_id=uuid4(),
        title="Active Project",
        project="AI",
        start_at=now,
        end_at=now,
        cpu_cores=8,
        memory_gb=32.0,
        gpu_count=1,
        gpu_ids=(0,),
        note=None,
        display_state=PlanDisplayState.ONGOING,
        cancelled_at=None,
        created_at=now,
        updated_at=now,
    )
    host_read = HostRuntimeRead(
        server_key="fwq51",
        display_name="fwq51",
        status=RuntimeStatus.ACTIVE,
        reported_at=now,
        freshness=FreshnessStatus.FRESH,
        gpus=[],
        ongoing_plans=[plan],
        unplanned_processes_count=0,
    )
    overview = RuntimeOverviewRead(
        servers=[host_read],
        observed_at=now,
    )
    dumped = overview.model_dump(mode="json")
    assert len(dumped["servers"]) == 1
    assert dumped["servers"][0]["server_key"] == "fwq51"
    assert dumped["servers"][0]["status"] == "active"
    assert dumped["servers"][0]["ongoing_plans"][0]["title"] == "Active Project"
