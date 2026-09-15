
from fastapi.testclient import TestClient

from .conftest import SERVER_ID, FakeCoreClient, conflict_read, plan_read


def test_schedule_renders_plans(client: TestClient, fake_core: FakeCoreClient) -> None:
    fake_core.plans.append(plan_read())

    response = client.get("/schedule")

    assert response.status_code == 200
    body = response.text
    assert "Schedule" in body
    assert "Alice" in body
    assert "RNA-seq" in body
    assert "08:00" in body and "13:00" in body
    assert "GPU 0" in body


def test_schedule_empty_state(client: TestClient) -> None:
    response = client.get("/schedule")

    assert response.status_code == 200
    assert "No planned use" in response.text


def test_schedule_filters_server_and_date(
    client: TestClient, fake_core: FakeCoreClient
) -> None:
    response = client.get("/schedule", params={"server": "fwq10", "date": "2026-09-20"})

    assert response.status_code == 200
    list_calls = [kwargs for name, kwargs in fake_core.calls if name == "list_plans"]
    assert list_calls, "expected list_plans to be called"
    call = list_calls[-1]
    assert call["server_id"] == SERVER_ID
    assert call["start"] is not None
    assert (call["start"].year, call["start"].month, call["start"].day) == (2026, 9, 20)
    assert (call["end"].year, call["end"].month, call["end"].day) == (2026, 9, 21)


def test_schedule_marks_overlap_warning(
    client: TestClient, fake_core: FakeCoreClient
) -> None:
    plan = plan_read()
    fake_core.plans.append(plan)
    fake_core._conflicts[plan.id] = [conflict_read(str(plan.id))]

    response = client.get("/schedule")

    assert response.status_code == 200
    assert "Overlap warning" in response.text


def test_schedule_form_uses_planned_use_language(client: TestClient) -> None:
    response = client.get("/schedule")

    assert response.status_code == 200
    body = response.text
    assert "Planned use" in body
    assert "Add planned use" in body


def test_schedule_does_not_render_approval_language(client: TestClient) -> None:
    response = client.get("/schedule")

    body = response.text.lower()
    for banned in ("approved", "reservation", "queue", "priority", "allocation"):
        assert banned not in body, f"must not render approval language: {banned}"


def test_schedule_post_translates_to_plan_create(
    client: TestClient, fake_core: FakeCoreClient
) -> None:
    response = client.post(
        "/schedule",
        data={
            "title": "Assembly",
            "server_key": "fwq10",
            "date": "2026-09-20",
            "start_at": "2026-09-20T14:00:00",
            "end_at": "2026-09-20T18:00:00",
            "cpu_cores": "32",
            "gpu_ids": "0,1",
            "note": "shared",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    creates = [value for name, value in fake_core.calls if name == "create_plan"]
    assert len(creates) == 1
    created = creates[0]
    assert created.title == "Assembly"
    assert created.server_id == SERVER_ID
    assert created.cpu_cores == 32
    assert created.gpu_ids == (0, 1)
    assert created.note == "shared"
    assert created.start_at.hour == 14 and created.start_at.utcoffset().total_seconds() == 0


def test_schedule_cancel_translates_to_core_cancel(
    client: TestClient, fake_core: FakeCoreClient
) -> None:
    plan = plan_read()
    fake_core.plans.append(plan)

    response = client.post(
        f"/schedule/{plan.id}/cancel", follow_redirects=False
    )

    assert response.status_code == 303
    cancels = [value for name, value in fake_core.calls if name == "cancel_plan"]
    assert [str(value) for value in cancels] == [str(plan.id)]
