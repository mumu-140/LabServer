from typing import Any

from fastapi.testclient import TestClient
from labserver_contracts.common import UserRole

from .conftest import ADMIN_ID, MEMBER_ID, OTHER_ID, SERVER_ID, ApiContext

START = "2026-09-20T08:00:00Z"
END = "2026-09-20T10:00:00Z"


def payload(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "server_id": str(SERVER_ID),
        "title": "RNA-seq",
        "start_at": START,
        "end_at": END,
    }
    body.update(overrides)
    return body


def as_member(api_context: ApiContext) -> TestClient:
    api_context.act_as(MEMBER_ID, UserRole.MEMBER)
    return api_context.client


def as_other(api_context: ApiContext) -> TestClient:
    api_context.act_as(OTHER_ID, UserRole.MEMBER)
    return api_context.client


def test_plan_endpoints_default_deny(api_context: ApiContext) -> None:
    client = api_context.client
    assert client.get("/api/v1/plans").status_code == 401
    assert client.post("/api/v1/plans", json=payload()).status_code == 401
    body = client.get("/api/v1/plans").json()
    assert body["error"]["code"] == "unauthorized"


def test_plan_create_is_direct_publication(api_context: ApiContext) -> None:
    client = as_member(api_context)

    response = client.post("/api/v1/plans", json=payload(gpu_count=1))
    assert response.status_code == 201
    body = response.json()
    assert "status" not in body
    assert "approved" not in body
    assert body["display_state"] == "upcoming"
    assert body["owner_id"] == str(MEMBER_ID)

    fetched = client.get(f"/api/v1/plans/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]


def test_plan_list_supports_filters(api_context: ApiContext) -> None:
    client = as_member(api_context)
    created = client.post(
        "/api/v1/plans", json=payload(start_at=START, end_at=END)
    ).json()

    listed = client.get(
        "/api/v1/plans",
        params={
            "server_id": str(SERVER_ID),
            "owner_id": str(MEMBER_ID),
            "start": "2026-09-20T08:30:00Z",
            "end": "2026-09-20T09:30:00Z",
        },
    )
    assert listed.status_code == 200
    assert [plan["id"] for plan in listed.json()] == [created["id"]]

    empty = client.get(
        "/api/v1/plans",
        params={"start": "2026-09-21T00:00:00Z", "end": "2026-09-21T01:00:00Z"},
    )
    assert empty.status_code == 200
    assert empty.json() == []


def test_plan_update_by_owner_and_forbidden_cross_owner(
    api_context: ApiContext,
) -> None:
    client = as_member(api_context)
    plan_id = client.post("/api/v1/plans", json=payload()).json()["id"]

    renamed = client.patch(f"/api/v1/plans/{plan_id}", json={"title": "Renamed"})
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Renamed"

    hijack = as_other(api_context).patch(
        f"/api/v1/plans/{plan_id}", json={"title": "Hijack"}
    )
    assert hijack.status_code == 403
    assert hijack.json()["error"]["code"] == "forbidden"


def test_plan_cancel_is_idempotent_and_default_excluded(
    api_context: ApiContext,
) -> None:
    client = as_member(api_context)
    plan_id = client.post("/api/v1/plans", json=payload()).json()["id"]

    cancelled = client.post(f"/api/v1/plans/{plan_id}/cancel")
    assert cancelled.status_code == 200
    first_cancelled_at = cancelled.json()["cancelled_at"]
    assert cancelled.json()["display_state"] == "cancelled"

    again = client.post(f"/api/v1/plans/{plan_id}/cancel")
    assert again.status_code == 200
    assert again.json()["cancelled_at"] == first_cancelled_at

    listed = client.get("/api/v1/plans")
    assert plan_id not in {plan["id"] for plan in listed.json()}

    including = client.get("/api/v1/plans", params={"include_cancelled": "true"})
    assert plan_id in {plan["id"] for plan in including.json()}


def test_plan_not_found_returns_404(api_context: ApiContext) -> None:
    client = as_member(api_context)
    missing = "00000000-0000-0000-0000-000000009999"
    assert client.get(f"/api/v1/plans/{missing}").status_code == 404
    assert client.patch(
        f"/api/v1/plans/{missing}", json={"title": "x"}
    ).status_code == 404
    assert client.post(f"/api/v1/plans/{missing}/cancel").status_code == 404
    assert client.get(f"/api/v1/plans/{missing}/conflicts").status_code == 404


def test_plan_invalid_interval_returns_422(api_context: ApiContext) -> None:
    client = as_member(api_context)
    response = client.post(
        "/api/v1/plans", json=payload(end_at="2026-09-20T07:00:00Z")
    )
    assert response.status_code == 422


def test_plan_conflicts_are_advisory_payloads(api_context: ApiContext) -> None:
    client = as_member(api_context)
    first = client.post(
        "/api/v1/plans",
        json=payload(title="First", gpu_count=1, gpu_ids=[0]),
    ).json()

    second = client.post(
        "/api/v1/plans",
        json=payload(
            title="Second",
            start_at="2026-09-20T08:30:00Z",
            end_at="2026-09-20T09:30:00Z",
            gpu_count=1,
            gpu_ids=[0],
        ),
    )
    # Overlap warns but never blocks publication.
    assert second.status_code == 201

    conflicts = client.get(f"/api/v1/plans/{second.json()['id']}/conflicts")
    assert conflicts.status_code == 200
    items = conflicts.json()
    assert len(items) == 1
    assert items[0]["resource"] == "gpu_device"
    assert items[0]["certainty"] == "confirmed"
    assert first["id"] in items[0]["conflicting_plan_ids"]


def test_plan_update_rejects_nulling_non_nullable_fields(
    api_context: ApiContext,
) -> None:
    client = as_member(api_context)
    plan_id = client.post("/api/v1/plans", json=payload()).json()["id"]

    for field in ("title", "start_at", "end_at"):
        response = client.patch(f"/api/v1/plans/{plan_id}", json={field: None})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"


def test_plan_update_validates_target_server_like_create(
    api_context: ApiContext,
) -> None:
    member = as_member(api_context)
    plan_id = member.post("/api/v1/plans", json=payload()).json()["id"]

    missing = member.patch(
        f"/api/v1/plans/{plan_id}",
        json={"server_id": "00000000-0000-0000-0000-000000009999"},
    )
    assert missing.status_code == 404

    api_context.act_as(ADMIN_ID, UserRole.ADMIN)
    disabled = api_context.client.post(
        "/api/v1/servers", json={"key": "fwq51", "display_name": "fwq51", "enabled": False}
    )
    assert disabled.status_code == 201, disabled.text
    disabled_id = disabled.json()["id"]

    api_context.act_as(MEMBER_ID, UserRole.MEMBER)
    moved = api_context.client.patch(
        f"/api/v1/plans/{plan_id}", json={"server_id": disabled_id}
    )
    assert moved.status_code == 409
    assert moved.json()["error"]["code"] == "server_disabled"


def test_plan_list_rejects_naive_datetime_filters(api_context: ApiContext) -> None:
    client = as_member(api_context)
    response = client.get(
        "/api/v1/plans", params={"start": "2026-09-20T08:00:00"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
