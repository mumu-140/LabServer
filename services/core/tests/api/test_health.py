from .conftest import ApiContext


def test_health_is_public_and_protected_routes_default_to_401(api_context: ApiContext) -> None:
    health = api_context.client.get("/healthz")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    protected = api_context.client.get("/api/v1/servers")
    assert protected.status_code == 401
    assert protected.json()["error"]["code"] == "unauthorized"
