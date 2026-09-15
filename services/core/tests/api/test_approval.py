from labserver_contracts.common import UserRole

from .conftest import ADMIN_ID, MEMBER_ID, SERVER_ID, ApiContext
from .test_requests import request_payload


def test_admin_approval_is_idempotent_and_reservation_is_queryable(api_context: ApiContext) -> None:
    api_context.act_as(MEMBER_ID, UserRole.MEMBER)
    created = api_context.client.post("/api/v1/requests", json=request_payload())
    request_id = created.json()["id"]
    submitted = api_context.client.post(f"/api/v1/requests/{request_id}/submit")
    assert submitted.status_code == 200

    api_context.act_as(ADMIN_ID, UserRole.ADMIN)
    approved = api_context.client.post(f"/api/v1/requests/{request_id}/approve")
    repeated = api_context.client.post(f"/api/v1/requests/{request_id}/approve")
    reservations = api_context.client.get(
        "/api/v1/reservations",
        params={
            "start": "2026-09-20T00:00:00Z",
            "end": "2026-09-21T00:00:00Z",
            "server_id": str(SERVER_ID),
        },
    )

    assert approved.status_code == 200
    assert approved.json()["status"] == "planned"
    assert repeated.status_code == 200
    assert repeated.json()["id"] == approved.json()["id"]
    assert reservations.status_code == 200
    assert [item["id"] for item in reservations.json()] == [approved.json()["id"]]


def test_member_cannot_approve_request(api_context: ApiContext) -> None:
    api_context.act_as(MEMBER_ID, UserRole.MEMBER)
    created = api_context.client.post("/api/v1/requests", json=request_payload())
    request_id = created.json()["id"]
    api_context.client.post(f"/api/v1/requests/{request_id}/submit")

    denied = api_context.client.post(f"/api/v1/requests/{request_id}/approve")

    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "forbidden"
