from labserver_contracts.common import UserRole

from .conftest import ADMIN_ID, MEMBER_ID, ApiContext


def test_member_can_list_logical_servers_but_cannot_create_them(api_context: ApiContext) -> None:
    api_context.act_as(MEMBER_ID, UserRole.MEMBER)

    listed = api_context.client.get("/api/v1/servers")
    denied = api_context.client.post(
        "/api/v1/servers",
        json={"key": "fwq51", "display_name": "fwq51", "cpu_cores": 32, "gpu_count": 2},
    )

    assert listed.status_code == 200
    assert listed.json()[0]["key"] == "fwq10"
    assert "ip" not in listed.json()[0]
    assert denied.status_code == 403


def test_admin_can_create_server_without_private_endpoint_field(api_context: ApiContext) -> None:
    api_context.act_as(ADMIN_ID, UserRole.ADMIN)

    created = api_context.client.post(
        "/api/v1/servers",
        json={
            "key": "fwq51",
            "display_name": "fwq51",
            "cpu_cores": 32,
            "memory_gb": 128.0,
            "gpu_count": 2,
        },
    )
    invalid = api_context.client.post(
        "/api/v1/servers",
        json={"key": "fwq56", "display_name": "fwq56", "ip": "192.0.2.56"},
    )

    assert created.status_code == 201
    assert created.json()["key"] == "fwq51"
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"
