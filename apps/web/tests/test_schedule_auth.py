from uuid import uuid4

from fastapi.testclient import TestClient

from .conftest import FakeCoreClient, plan_read


def test_schedule_is_default_deny_without_viewer(anonymous_client: TestClient) -> None:
    response = anonymous_client.get("/schedule")

    assert response.status_code == 401


def test_anonymous_edit_is_401(anonymous_client: TestClient) -> None:
    plan_id = str(uuid4())

    response = anonymous_client.get(f"/schedule/{plan_id}/edit")

    assert response.status_code == 401


def test_owner_sees_edit_and_cancel(
    client: TestClient, fake_core: FakeCoreClient
) -> None:
    plan = plan_read()
    fake_core.plans.append(plan)

    response = client.get("/schedule")

    assert response.status_code == 200
    body = response.text
    assert f"/schedule/{plan.id}/edit" in body
    assert f"/schedule/{plan.id}/cancel" in body


def test_other_member_sees_neither_edit_nor_cancel(
    bob_client: TestClient, fake_core: FakeCoreClient
) -> None:
    plan = plan_read()
    fake_core.plans.append(plan)

    response = bob_client.get("/schedule")

    assert response.status_code == 200
    body = response.text
    assert f"/schedule/{plan.id}/edit" not in body
    assert f"/schedule/{plan.id}/cancel" not in body


def test_admin_sees_edit_and_cancel_for_any_plan(
    admin_client: TestClient, fake_core: FakeCoreClient
) -> None:
    plan = plan_read()
    fake_core.plans.append(plan)

    response = admin_client.get("/schedule")

    assert response.status_code == 200
    body = response.text
    assert f"/schedule/{plan.id}/edit" in body
    assert f"/schedule/{plan.id}/cancel" in body


def test_edit_form_renders_for_owner(
    client: TestClient, fake_core: FakeCoreClient
) -> None:
    plan = plan_read()
    fake_core.plans.append(plan)

    response = client.get(f"/schedule/{plan.id}/edit")

    assert response.status_code == 200


def test_edit_denied_for_other_member(
    bob_client: TestClient, fake_core: FakeCoreClient
) -> None:
    plan = plan_read()
    fake_core.plans.append(plan)

    response = bob_client.get(f"/schedule/{plan.id}/edit")

    assert response.status_code == 403


def test_edit_denied_for_other_member_on_post(
    bob_client: TestClient, fake_core: FakeCoreClient
) -> None:
    plan = plan_read()
    fake_core.plans.append(plan)

    response = bob_client.post(
        f"/schedule/{plan.id}/edit",
        data={
            "title": "hijack",
            "start_at": "2026-09-21T10:00",
            "end_at": "2026-09-21T12:00",
        },
    )

    assert response.status_code == 403


def test_edit_translates_local_input_to_utc(
    client: TestClient, fake_core: FakeCoreClient
) -> None:
    plan = plan_read()
    fake_core.plans.append(plan)

    response = client.post(
        f"/schedule/{plan.id}/edit",
        data={
            "title": "RNA-seq",
            "start_at": "2026-09-20T14:00",
            "end_at": "2026-09-20T19:00",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    updates = [payload for name, payload in fake_core.calls if name == "update_plan"]
    assert updates, "expected update_plan to be called"
    data = updates[-1]["data"]
    assert data.start_at is not None
    assert data.start_at.isoformat() == "2026-09-20T06:00:00+00:00"
    assert data.end_at is not None
    assert data.end_at.isoformat() == "2026-09-20T11:00:00+00:00"
