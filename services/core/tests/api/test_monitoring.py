from datetime import UTC, datetime, timedelta
from uuid import uuid4

from labserver_contracts.common import UserRole
from labserver_contracts.monitoring import (
    FreshnessStatus,
    HostMetricsRead,
    HostStatus,
)
from labserver_core.adapters.monitoring import FakeHostMetricsProvider
from labserver_core.domain.entities import PlanEntry
from labserver_core.persistence.repositories import PlanRepository

from .conftest import MEMBER_ID, SERVER_ID, ApiContext


def test_unauthenticated_dashboard_returns_401(api_context: ApiContext) -> None:
    api_context.clear_actor()
    resp = api_context.client.get("/api/v1/monitoring/dashboard")
    assert resp.status_code == 401


def test_member_can_view_dashboard_with_metrics_and_plans(api_context: ApiContext) -> None:
    api_context.act_as(MEMBER_ID, UserRole.MEMBER)

    # Configure fake metrics provider on app
    provider = FakeHostMetricsProvider()
    provider.set_metrics(
        "fwq10",
        HostMetricsRead(
            server_key="fwq10",
            status=HostStatus.UP,
            freshness=FreshnessStatus.FRESH,
            cpu_percent=18.5,
            memory_percent=40.0,
            memory_total_gb=256.0,
            memory_used_gb=102.4,
            disk_percent=35.0,
            upstream_url="https://beszel.example.com/system/fwq10",
        ),
    )
    api_context.app.state.metrics_provider = provider

    # Seed a plan in SQLite for fwq10
    now = datetime.now(UTC)
    with api_context.session_factory() as session:
        plans = PlanRepository(session)
        plans.add(
            PlanEntry(
                id=uuid4(),
                owner_id=MEMBER_ID,
                server_id=SERVER_ID,
                title="Poplar Genomic Indexing",
                project="Poplar",
                start_at=now - timedelta(minutes=30),
                end_at=now + timedelta(hours=2),
                cpu_cores=16,
                memory_gb=64.0,
                gpu_count=1,
                gpu_ids=(0,),
                note="Building index",
                cancelled_at=None,
                created_at=now,
                updated_at=now,
            )
        )

        session.commit()

    resp = api_context.client.get("/api/v1/monitoring/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert "cards" in data
    assert len(data["cards"]) >= 1

    card = next(c for c in data["cards"] if c["server"]["key"] == "fwq10")
    assert card["server"]["key"] == "fwq10"
    assert card["metrics"] is not None
    assert card["metrics"]["status"] == "up"
    assert card["metrics"]["freshness"] == "fresh"
    assert card["metrics"]["cpu_percent"] == 18.5
    assert card["metrics"]["memory_used_gb"] == 102.4
    assert card["active_plans_count"] == 1
    assert len(card["near_term_plans"]) == 1
    assert card["near_term_plans"][0]["title"] == "Poplar Genomic Indexing"
    assert card["near_term_plans"][0]["display_state"] == "ongoing"


def test_get_server_metrics_endpoints(api_context: ApiContext) -> None:
    api_context.act_as(MEMBER_ID, UserRole.MEMBER)

    provider = FakeHostMetricsProvider()
    provider.set_metrics(
        "fwq10",
        HostMetricsRead(
            server_key="fwq10",
            status=HostStatus.UP,
            freshness=FreshnessStatus.FRESH,
            cpu_percent=12.0,
        ),
    )
    api_context.app.state.metrics_provider = provider

    resp = api_context.client.get("/api/v1/monitoring/servers/fwq10")
    assert resp.status_code == 200
    assert resp.json()["server_key"] == "fwq10"
    assert resp.json()["cpu_percent"] == 12.0

    not_found = api_context.client.get("/api/v1/monitoring/servers/nonexistent")
    assert not_found.status_code == 404
