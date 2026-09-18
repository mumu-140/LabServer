from dataclasses import replace
from datetime import UTC, datetime

from labserver_contracts.common import UserRole
from labserver_contracts.runtime import RuntimeStatus

from .conftest import MEMBER_ID, ApiContext


def test_unauthenticated_runtime_endpoints_return_401(api_context: ApiContext) -> None:
    api_context.clear_actor()
    r1 = api_context.client.get("/api/v1/runtime/overview")
    assert r1.status_code == 401

    r2 = api_context.client.get("/api/v1/runtime/servers/fwq10")
    assert r2.status_code == 401


def test_collector_token_authentication(api_context: ApiContext) -> None:
    current_settings = api_context.app.state.settings
    api_context.app.state.settings = replace(current_settings, collector_token="test-token-xyz")

    payload = {
        "server_key": "fwq10",
        "reported_at": datetime.now(UTC).isoformat(),
        "gpus": [],
    }

    # 1. No token -> 403
    r_none = api_context.client.post("/api/v1/runtime/report", json=payload)
    assert r_none.status_code == 403

    # 2. Wrong token -> 403
    r_bad = api_context.client.post(
        "/api/v1/runtime/report",
        json=payload,
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert r_bad.status_code == 403

    # 3. Correct token via Bearer -> 200
    r_ok1 = api_context.client.post(
        "/api/v1/runtime/report",
        json=payload,
        headers={"Authorization": "Bearer test-token-xyz"},
    )
    assert r_ok1.status_code == 200
    assert r_ok1.json() == {"status": "ok"}

    # 4. Correct token via X-Collector-Token -> 200
    r_ok2 = api_context.client.post(
        "/api/v1/runtime/report",
        json=payload,
        headers={"X-Collector-Token": "test-token-xyz"},
    )
    assert r_ok2.status_code == 200


def test_member_can_view_runtime_overview_and_server_runtime(api_context: ApiContext) -> None:
    api_context.act_as(MEMBER_ID, UserRole.MEMBER)
    now = datetime.now(UTC)

    # Submit runtime report
    report_payload = {
        "server_key": "fwq10",
        "reported_at": now.isoformat(),
        "gpus": [
            {
                "index": 0,
                "name": "NVIDIA A100",
                "memory_total_mb": 40960.0,
                "memory_used_mb": 8192.0,
                "utilization_gpu_percent": 65.0,
                "temperature_celsius": 54,
                "processes": [
                    {
                        "gpu_id": 0,
                        "pid": 54321,
                        "process_name": "python fine_tune.py",
                        "username": "member",
                        "used_memory_mb": 8000.0,
                    }
                ],
            }
        ],
    }
    r_submit = api_context.client.post("/api/v1/runtime/report", json=report_payload)
    assert r_submit.status_code == 200

    # Overview endpoint
    r_overview = api_context.client.get("/api/v1/runtime/overview")
    assert r_overview.status_code == 200
    data = r_overview.json()
    assert "servers" in data
    assert len(data["servers"]) >= 1
    fwq10 = next(s for s in data["servers"] if s["server_key"] == "fwq10")
    assert fwq10["status"] == RuntimeStatus.ACTIVE.value
    assert len(fwq10["gpus"]) == 1
    assert fwq10["gpus"][0]["name"] == "NVIDIA A100"

    # Server detail endpoint
    r_server = api_context.client.get("/api/v1/runtime/servers/fwq10")
    assert r_server.status_code == 200
    server_data = r_server.json()
    assert server_data["server_key"] == "fwq10"
    assert len(server_data["gpus"]) == 1
    p = server_data["gpus"][0]["processes"][0]
    assert p["pid"] == 54321
    assert p["username"] == "member"


def test_server_runtime_not_found(api_context: ApiContext) -> None:
    api_context.act_as(MEMBER_ID, UserRole.MEMBER)
    r = api_context.client.get("/api/v1/runtime/servers/nonexistent_key")
    assert r.status_code == 404
