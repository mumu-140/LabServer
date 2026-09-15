from labserver_contracts.common import UserRole

from .conftest import MEMBER_ID, SERVER_ID, ApiContext


def request_payload() -> dict[str, object]:
    return {
        "title": "Poplar assembly",
        "project": "Populus",
        "preferred_server_id": str(SERVER_ID),
        "planned_start": "2026-09-20T08:00:00Z",
        "planned_duration_minutes": 120,
        "requested_cpu_cores": 32,
        "requested_memory_gb": 128.0,
        "requested_gpu_count": 2,
        "preferred_gpu_ids": [0, 1],
    }


def test_member_request_crud_and_invalid_transition_error(api_context: ApiContext) -> None:
    api_context.act_as(MEMBER_ID, UserRole.MEMBER)

    created = api_context.client.post("/api/v1/requests", json=request_payload())
    request_id = created.json()["id"]
    listed = api_context.client.get("/api/v1/requests")
    fetched = api_context.client.get(f"/api/v1/requests/{request_id}")
    updated = api_context.client.patch(
        f"/api/v1/requests/{request_id}", json={"title": "Updated assembly"}
    )
    submitted = api_context.client.post(f"/api/v1/requests/{request_id}/submit")
    repeated_submit = api_context.client.post(f"/api/v1/requests/{request_id}/submit")

    assert created.status_code == 201
    assert created.json()["status"] == "draft"
    assert [item["id"] for item in listed.json()] == [request_id]
    assert fetched.json()["id"] == request_id
    assert updated.json()["title"] == "Updated assembly"
    assert submitted.json()["status"] == "submitted"
    assert repeated_submit.status_code == 409
    assert repeated_submit.json()["error"]["code"] == "invalid_transition"


def test_conflict_preview_endpoint_returns_advisory_list(api_context: ApiContext) -> None:
    api_context.act_as(MEMBER_ID, UserRole.MEMBER)
    created = api_context.client.post("/api/v1/requests", json=request_payload())
    request_id = created.json()["id"]

    preview = api_context.client.get(f"/api/v1/requests/{request_id}/conflicts")

    assert preview.status_code == 200
    assert preview.json() == []
