from datetime import UTC, datetime, timedelta

import httpx
import pytest
from labserver_contracts.monitoring import (
    FreshnessStatus,
    HostMetricsRead,
    HostStatus,
)
from labserver_core.adapters.monitoring import (
    BeszelAdapter,
    FakeHostMetricsProvider,
)


@pytest.mark.anyio
async def test_fake_host_metrics_provider() -> None:
    provider = FakeHostMetricsProvider()
    metrics = await provider.get_metrics(["fwq10"])
    assert "fwq10" in metrics
    assert metrics["fwq10"].status == HostStatus.UNKNOWN
    assert metrics["fwq10"].freshness == FreshnessStatus.UNKNOWN

    provider.set_metrics(
        "fwq10",
        HostMetricsRead(
            server_key="fwq10",
            status=HostStatus.UP,
            freshness=FreshnessStatus.FRESH,
            cpu_percent=25.0,
        ),
    )
    single = await provider.get_server_metrics("fwq10")
    assert single.status == HostStatus.UP
    assert single.cpu_percent == 25.0


@pytest.mark.anyio
async def test_beszel_adapter_successful_fetch_and_mapping() -> None:
    now_iso = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.000Z")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/collections/_superusers/auth-with-password":
            return httpx.Response(200, json={"token": "test-superuser-token"})
        if request.url.path == "/api/collections/systems/records":
            auth = request.headers.get("Authorization")
            assert auth == "Bearer test-superuser-token"
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "sys104",
                            "name": "azure104",
                            "status": "up",
                            "updated": now_iso,
                            "info": {
                                "cpu": 5.5,
                                "mp": 60.0,
                                "dp": 30.0,
                                "u": 100000,
                                "la": [0.5, 0.3, 0.1],
                            },
                        },
                        {
                            "id": "sys10",
                            "name": "fwq10ys",
                            "status": "up",
                            "updated": now_iso,
                            "info": {
                                "cpu": 15.2,
                                "mp": 50.0,
                                "dp": 40.0,
                                "u": 200000,
                                "la": [1.5, 1.2, 0.8],
                                "d": 2000.0,
                                "du": 800.0,
                            },
                        },
                    ]
                },
            )
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = BeszelAdapter(
        hub_url="http://mock-beszel:8090",
        public_url="https://beszel.example.com",
        username="admin@example.com",
        password="secretpassword",
        key_map={"fwq10": "fwq10ys"},
        http_client=client,
    )

    metrics = await adapter.get_metrics(
        ["fwq10", "unknown_srv"],
        server_capacities={"fwq10": (256.0, 48)},
    )

    assert "fwq10" in metrics
    fwq = metrics["fwq10"]
    assert fwq.server_key == "fwq10"
    assert fwq.status == HostStatus.UP
    assert fwq.freshness == FreshnessStatus.FRESH
    assert fwq.cpu_percent == 15.2
    assert fwq.memory_percent == 50.0
    assert fwq.memory_total_gb == 256.0
    assert fwq.memory_used_gb == 128.0
    assert fwq.disk_percent == 40.0
    assert fwq.disk_total_gb == 2000.0
    assert fwq.disk_used_gb == 800.0
    assert fwq.uptime_seconds == 200000
    assert fwq.load_average == (1.5, 1.2, 0.8)
    assert fwq.upstream_url == "https://beszel.example.com/system/fwq10ys"

    unk = metrics["unknown_srv"]
    assert unk.status == HostStatus.UNKNOWN
    assert unk.freshness == FreshnessStatus.UNKNOWN


@pytest.mark.anyio
async def test_beszel_adapter_token_refresh_on_401() -> None:
    now_iso = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.000Z")
    call_count = {"systems": 0, "auth": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if "/auth-with-password" in request.url.path:
            call_count["auth"] += 1
            return httpx.Response(200, json={"token": f"token-{call_count['auth']}"})
        if request.url.path == "/api/collections/systems/records":
            call_count["systems"] += 1
            if call_count["systems"] == 1:
                return httpx.Response(401, json={"message": "token expired"})
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "sys1",
                            "name": "fwq10",
                            "status": "up",
                            "updated": now_iso,
                            "info": {"cpu": 10.0},
                        }
                    ]
                },
            )
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = BeszelAdapter(
        hub_url="http://mock-beszel:8090",
        username="admin@example.com",
        password="secretpassword",
        token="initial-token",
        http_client=client,
    )
    # Clear static token flag so it allows refresh
    adapter._static_token = False

    metrics = await adapter.get_metrics(["fwq10"])
    assert metrics["fwq10"].status == HostStatus.UP
    assert metrics["fwq10"].cpu_percent == 10.0
    assert call_count["systems"] == 2
    assert call_count["auth"] == 1


@pytest.mark.anyio
async def test_beszel_adapter_stale_and_down_freshness() -> None:
    old_iso = (datetime.now(UTC) - timedelta(seconds=300)).strftime("%Y-%m-%d %H:%M:%S.000Z")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "sys1",
                        "name": "stale_srv",
                        "status": "up",
                        "updated": old_iso,
                        "info": {"cpu": 5.0},
                    },
                    {
                        "id": "sys2",
                        "name": "down_srv",
                        "status": "down",
                        "updated": old_iso,
                        "info": {},
                    },
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = BeszelAdapter(
        hub_url="http://mock-beszel:8090",
        token="valid-token",
        freshness_threshold_seconds=60.0,
        http_client=client,
    )

    metrics = await adapter.get_metrics(["stale_srv", "down_srv"])
    assert metrics["stale_srv"].status == HostStatus.UP
    assert metrics["stale_srv"].freshness == FreshnessStatus.STALE

    assert metrics["down_srv"].status == HostStatus.DOWN
    assert metrics["down_srv"].freshness == FreshnessStatus.UNREACHABLE


@pytest.mark.anyio
async def test_beszel_adapter_hub_unreachable_fallback() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = BeszelAdapter(
        hub_url="http://down-hub:8090",
        token="valid-token",
        http_client=client,
    )

    metrics = await adapter.get_metrics(["fwq10"])
    assert metrics["fwq10"].status == HostStatus.UNKNOWN
    assert metrics["fwq10"].freshness == FreshnessStatus.UNREACHABLE
    assert metrics["fwq10"].error_message is not None
    assert "Connection refused" in metrics["fwq10"].error_message


@pytest.mark.anyio
async def test_beszel_adapter_caching_within_ttl() -> None:
    call_count = {"systems": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["systems"] += 1
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "sys1",
                        "name": "fwq10",
                        "status": "up",
                        "updated": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.000Z"),
                        "info": {"cpu": 12.0},
                    }
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = BeszelAdapter(
        hub_url="http://mock-beszel:8090",
        token="valid-token",
        cache_ttl_seconds=10.0,
        http_client=client,
    )

    m1 = await adapter.get_metrics(["fwq10"])
    m2 = await adapter.get_metrics(["fwq10"])
    assert m1["fwq10"].cpu_percent == 12.0
    assert m2["fwq10"].cpu_percent == 12.0
    assert call_count["systems"] == 1
