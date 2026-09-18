from labserver_contracts.common import UserRole

from .conftest import ADMIN_ID, MEMBER_ID, OTHER_ID, ApiContext


def test_member_can_list_users_but_cannot_create(api_context: ApiContext) -> None:
    api_context.act_as(MEMBER_ID, UserRole.MEMBER)

    listed = api_context.client.get("/api/v1/users")
    created = api_context.client.post(
        "/api/v1/users",
        json={"username": "blocked", "display_name": "Blocked", "role": "member"},
    )

    assert listed.status_code == 200
    assert {item["username"] for item in listed.json()} == {"admin", "member", "other"}
    assert created.status_code == 403
    assert created.json()["error"]["code"] == "forbidden"


def test_admin_can_list_and_create_user(api_context: ApiContext) -> None:
    api_context.act_as(ADMIN_ID, UserRole.ADMIN)

    listed = api_context.client.get("/api/v1/users")
    created = api_context.client.post(
        "/api/v1/users",
        json={"username": "scientist", "display_name": "Scientist", "role": "member"},
    )

    assert listed.status_code == 200
    assert {item["username"] for item in listed.json()} == {"admin", "member", "other"}
    assert created.status_code == 201
    assert created.json()["username"] == "scientist"


def test_member_cannot_update_user(api_context: ApiContext) -> None:
    api_context.act_as(MEMBER_ID, UserRole.MEMBER)
    resp = api_context.client.patch(
        f"/api/v1/users/{OTHER_ID}",
        json={"display_name": "Hacked"},
    )
    assert resp.status_code == 403


def test_admin_can_update_user_and_cannot_disable_self(api_context: ApiContext) -> None:
    api_context.act_as(ADMIN_ID, UserRole.ADMIN)

    resp = api_context.client.patch(
        f"/api/v1/users/{OTHER_ID}",
        json={"display_name": "Updated Other", "enabled": False},
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Updated Other"
    assert resp.json()["enabled"] is False

    resp_self = api_context.client.patch(
        f"/api/v1/users/{ADMIN_ID}",
        json={"enabled": False},
    )
    assert resp_self.status_code == 422
    assert resp_self.json()["error"]["message"] == "Cannot disable your own account"
