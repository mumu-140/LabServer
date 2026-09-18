from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient
from labserver_contracts.monitoring import (
    DashboardRead,
    FreshnessStatus,
    HostMetricsRead,
    HostStatus,
    ServerDashboardCard,
)
from labserver_contracts.plans import PlanDisplayState, PlanRead
from labserver_web.clients.core import CoreClientError

from .conftest import FakeCoreClient, server_read



def test_anonymous_dashboard_is_401(anonymous_client: TestClient) -> None:
    resp_root = anonymous_client.get("/")
    assert resp_root.status_code == 401

    resp_dash = anonymous_client.get("/dashboard")
    assert resp_dash.status_code == 401


def test_authenticated_member_sees_dashboard_cards(
    client: TestClient, fake_core: FakeCoreClient
) -> None:
    server = server_read(key="fwq10", display_name="fwq10")
    fake_core.servers = [server]

    now = datetime.now(UTC)
    dashboard = DashboardRead(
        cards=[
            ServerDashboardCard(
                server=server,
                metrics=HostMetricsRead(
                    server_key="fwq10",
                    status=HostStatus.UP,
                    freshness=FreshnessStatus.FRESH,
                    cpu_percent=24.5,
                    memory_percent=60.0,
                    memory_used_gb=153.6,
                    memory_total_gb=256.0,
                    disk_percent=45.0,
                    disk_used_gb=900.0,
                    disk_total_gb=2000.0,
                    load_average=(1.5, 1.2, 0.8),
                    uptime_seconds=360000,
                    upstream_url="https://beszel.example.com/system/fwq10",
                ),
                active_plans_count=1,
                near_term_plans=[
                    PlanRead(
                        id=UUID("00000000-0000-0000-0000-000000000001"),
                        owner_id=UUID("00000000-0000-0000-0000-000000000002"),
                        server_id=server.id,
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
                ],
            )
        ],
        observed_at=now,
    )
    fake_core.dashboard = dashboard

    response = client.get("/dashboard")
    assert response.status_code == 200
    body = response.text

    assert "fwq10" in body
    assert "● Up" in body
    assert "24.5%" in body
    assert "60.0%" in body
    assert "45.0%" in body
    assert "1 active" in body
    assert "RNA-seq assembly" in body
    assert "https://beszel.example.com/system/fwq10" in body
    assert "/schedule?server=fwq10" in body


def test_dashboard_renders_status_badges(
    client: TestClient, fake_core: FakeCoreClient
) -> None:
    s1 = server_read(server_id=UUID("00000000-0000-0000-0000-000000000011"), key="fwq51", display_name="fwq51")
    s2 = server_read(server_id=UUID("00000000-0000-0000-0000-000000000012"), key="fwq56", display_name="fwq56")

    now = datetime.now(UTC)
    dashboard = DashboardRead(
        cards=[
            ServerDashboardCard(
                server=s1,
                metrics=HostMetricsRead(
                    server_key="fwq51",
                    status=HostStatus.UP,
                    freshness=FreshnessStatus.STALE,
                    cpu_percent=5.0,
                ),
            ),
            ServerDashboardCard(
                server=s2,
                metrics=HostMetricsRead(
                    server_key="fwq56",
                    status=HostStatus.DOWN,
                    freshness=FreshnessStatus.UNREACHABLE,
                ),
            ),
        ],
        observed_at=now,
    )
    fake_core.dashboard = dashboard

    response = client.get("/dashboard")
    assert response.status_code == 200
    body = response.text

    assert "fwq51" in body
    assert "▲ Stale" in body
    assert "fwq56" in body
    assert "■ Down" in body


def test_dashboard_core_failure_renders_error(
    client: TestClient, fake_core: FakeCoreClient
) -> None:
    fake_core.error = CoreClientError(503, "service_unavailable", "Database is unavailable")
    response = client.get("/dashboard")
    assert response.status_code == 503
    assert "Database is unavailable" in response.text
