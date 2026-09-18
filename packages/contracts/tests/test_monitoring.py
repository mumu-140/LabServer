from datetime import datetime
from uuid import UUID

import pytest
from labserver_contracts.monitoring import (
    DashboardRead,
    FreshnessStatus,
    GpuMetricsRead,
    HostMetricsRead,
    HostStatus,
    ServerDashboardCard,
)
from labserver_contracts.plans import PlanDisplayState, PlanRead
from labserver_contracts.servers import ServerRead
from pydantic import ValidationError


def test_monitoring_enums_are_stable() -> None:
    assert [s.value for s in HostStatus] == ["up", "down", "unknown"]
    assert [f.value for f in FreshnessStatus] == [
        "fresh",
        "stale",
        "unreachable",
        "disabled",
        "unknown",
    ]


def test_host_metrics_read_serialization() -> None:
    metrics = HostMetricsRead.model_validate(
        {
            "server_key": "fwq10",
            "status": "up",
            "freshness": "fresh",
            "cpu_percent": 12.5,
            "memory_used_gb": 64.0,
            "memory_total_gb": 256.0,
            "memory_percent": 25.0,
            "disk_used_gb": 500.0,
            "disk_total_gb": 2000.0,
            "disk_percent": 25.0,
            "load_average": (1.2, 0.8, 0.5),
            "uptime_seconds": 123456,
            "gpus": [
                {
                    "index": 0,
                    "name": "NVIDIA A100-PCIE-40GB",
                    "utilization_percent": 45.0,
                    "memory_used_gb": 16.0,
                    "memory_total_gb": 40.0,
                    "temperature_c": 55,
                }
            ],
            "upstream_url": "https://beszel.example.com/system/fwq10",
            "updated_at": "2026-09-18T10:00:00+08:00",
            "error_message": None,
        }
    )

    data = metrics.model_dump(mode="json")
    assert data["server_key"] == "fwq10"
    assert data["status"] == "up"
    assert data["freshness"] == "fresh"
    assert data["cpu_percent"] == 12.5
    assert data["memory_percent"] == 25.0
    assert data["load_average"] == [1.2, 0.8, 0.5]
    assert data["gpus"][0]["name"] == "NVIDIA A100-PCIE-40GB"
    assert data["updated_at"] == "2026-09-18T02:00:00Z"


def test_host_metrics_read_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        HostMetricsRead.model_validate(
            {
                "server_key": "fwq10",
                "status": "up",
                "freshness": "fresh",
                "unexpected_field": 123,
            }
        )


def test_dashboard_read_roundtrip() -> None:
    now = datetime.fromisoformat("2026-09-18T02:00:00Z")
    server = ServerRead(
        id=UUID("00000000-0000-0000-0000-000000000010"),
        key="fwq10",
        display_name="fwq10",
        enabled=True,
        cpu_cores=48,
        memory_gb=256.0,
        gpu_count=4,
        created_at=now,
        updated_at=now,
    )
    plan = PlanRead(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        owner_id=UUID("00000000-0000-0000-0000-000000000002"),
        server_id=server.id,
        title="Genome Assembly",
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
    metrics = HostMetricsRead(
        server_key="fwq10",
        status=HostStatus.UP,
        freshness=FreshnessStatus.FRESH,
        cpu_percent=15.0,
        memory_used_gb=38.4,
        memory_total_gb=256.0,
        memory_percent=15.0,
    )
    card = ServerDashboardCard(
        server=server,
        metrics=metrics,
        active_plans_count=1,
        near_term_plans=[plan],
    )
    dashboard = DashboardRead(
        cards=[card],
        observed_at=now,
    )

    dumped = dashboard.model_dump(mode="json")
    assert len(dumped["cards"]) == 1
    assert dumped["cards"][0]["server"]["key"] == "fwq10"
    assert dumped["cards"][0]["metrics"]["cpu_percent"] == 15.0
    assert dumped["cards"][0]["active_plans_count"] == 1
    assert dumped["cards"][0]["near_term_plans"][0]["title"] == "Genome Assembly"

    reloaded = DashboardRead.model_validate(dumped)
    assert reloaded.cards[0].server.key == "fwq10"
    assert reloaded.cards[0].metrics is not None
    assert reloaded.cards[0].metrics.status == HostStatus.UP
