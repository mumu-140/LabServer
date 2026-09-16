from datetime import UTC, datetime
from uuid import uuid4

import labserver_web.routes.schedule as schedule_module
import pytest
from fastapi.testclient import TestClient

from .conftest import ALICE_ID, NOW, SERVER_ID, FakeCoreClient, conflict_read, plan_read


def test_schedule_renders_plans(
    client: TestClient,
    fake_core: FakeCoreClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_core.plans.append(plan_read())
    monkeypatch.setattr(
        schedule_module, "_now_utc", lambda: datetime(2026, 9, 20, 4, 0, tzinfo=UTC)
    )

    response = client.get("/schedule")

    assert response.status_code == 200
    body = response.text
    assert "Schedule" in body
    assert "Alice" in body
    assert "RNA-seq" in body
    assert "16:00" in body and "21:00" in body
    assert "GPU 0" in body


def test_schedule_empty_state(client: TestClient) -> None:
    response = client.get("/schedule")

    assert response.status_code == 200
    assert "No planned use" in response.text


def test_schedule_renders_timezone_label(client: TestClient) -> None:
    response = client.get("/schedule")

    assert response.status_code == 200
    assert "Asia/Shanghai" in response.text


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
    assert call["start"] == datetime(2026, 9, 19, 16, 0, tzinfo=UTC)
    assert call["end"] == datetime(2026, 9, 20, 16, 0, tzinfo=UTC)


def test_server_filter_renders_only_selected_group(
    client: TestClient,
    fake_core: FakeCoreClient,
) -> None:
    response = client.get("/schedule", params={"server": "fwq10", "date": "2026-09-20"})

    assert response.status_code == 200
    assert "fwq10" in response.text
    assert "fwq51" not in response.text


def test_unknown_server_filter_returns_422(client: TestClient) -> None:
    response = client.get("/schedule", params={"server": "missing", "date": "2026-09-20"})

    assert response.status_code == 422


def test_owner_filter_reaches_core(
    client: TestClient,
    fake_core: FakeCoreClient,
) -> None:
    response = client.get(
        "/schedule",
        params={"owner": str(ALICE_ID), "date": "2026-09-20"},
    )

    assert response.status_code == 200
    list_calls = [payload for name, payload in fake_core.calls if name == "list_plans"]
    assert list_calls[-1]["owner_id"] == ALICE_ID


def test_unknown_owner_filter_returns_422(client: TestClient) -> None:
    response = client.get(
        "/schedule", params={"owner": str(uuid4()), "date": "2026-09-20"}
    )

    assert response.status_code == 422


def test_default_date_resolves_to_today_in_configured_timezone(
    client: TestClient,
    fake_core: FakeCoreClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(schedule_module, "_now_utc", lambda: NOW)

    response = client.get("/schedule")

    assert response.status_code == 200
    list_calls = [kwargs for name, kwargs in fake_core.calls if name == "list_plans"]
    call = list_calls[-1]
    assert call["start"] == datetime(2026, 9, 14, 16, 0, tzinfo=UTC)
    assert call["end"] == datetime(2026, 9, 15, 16, 0, tzinfo=UTC)


def test_cross_day_window_is_annotated_in_local_time(
    client: TestClient,
    fake_core: FakeCoreClient,
) -> None:
    plan = plan_read(start_at="2026-09-19T14:00:00Z", end_at="2026-09-20T02:00:00Z")
    fake_core.plans.append(plan)

    response = client.get("/schedule", params={"date": "2026-09-20"})

    assert response.status_code == 200
    assert "09-19 22:00" in response.text
    assert "10:00" in response.text


def test_schedule_marks_overlap_warning(
    client: TestClient, fake_core: FakeCoreClient
) -> None:
    plan = plan_read()
    fake_core.plans.append(plan)
    fake_core._conflicts[plan.id] = [conflict_read(str(plan.id))]

    response = client.get("/schedule")

    assert response.status_code == 200
    assert "Overlap warning" in response.text


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
