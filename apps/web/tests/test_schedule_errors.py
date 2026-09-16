import pytest
from fastapi.testclient import TestClient
from labserver_web.clients.core import CoreClientError, CoreUnavailableError

from .conftest import FakeCoreClient, plan_read

BASE_FORM = {
    "title": "Assembly",
    "server_key": "fwq10",
    "date": "2026-09-20",
    "start_at": "2026-09-20T14:00",
    "end_at": "2026-09-20T18:00",
    "cpu_cores": "32",
    "memory_gb": "64",
    "gpu_count": "1",
    "gpu_ids": "0",
    "note": "shared",
}


def _mutate(**overrides: str) -> dict[str, str]:
    values = dict(BASE_FORM)
    values.update(overrides)
    return values


def test_cpu_cores_letters_render_422(
    client: TestClient, fake_core: FakeCoreClient
) -> None:
    response = client.post("/schedule", data=_mutate(cpu_cores="abc"))

    assert response.status_code == 422
    assert "traceback" not in response.text.lower()


def test_memory_gb_letters_render_422(
    client: TestClient, fake_core: FakeCoreClient
) -> None:
    response = client.post("/schedule", data=_mutate(memory_gb="abc"))

    assert response.status_code == 422
    assert "traceback" not in response.text.lower()


def test_gpu_ids_unknown_token_render_422(
    client: TestClient, fake_core: FakeCoreClient
) -> None:
    response = client.post("/schedule", data=_mutate(gpu_ids="0,x"))

    assert response.status_code == 422
    assert "traceback" not in response.text.lower()


def test_end_before_start_renders_422(
    client: TestClient, fake_core: FakeCoreClient
) -> None:
    response = client.post("/schedule", data=_mutate(end_at="2026-09-20T10:00"))

    assert response.status_code == 422
    assert "traceback" not in response.text.lower()


def test_gpu_count_mismatch_renders_422(
    client: TestClient, fake_core: FakeCoreClient
) -> None:
    response = client.post("/schedule", data=_mutate(gpu_count="1", gpu_ids="0,1"))

    assert response.status_code == 422
    assert "traceback" not in response.text.lower()


@pytest.mark.parametrize("status", [401, 403, 404, 409, 422])
def test_core_mutation_errors_render_same_status(
    client: TestClient,
    fake_core: FakeCoreClient,
    status: int,
) -> None:
    fake_core.error = CoreClientError(status, "error", "core said no")

    response = client.post("/schedule", data=BASE_FORM)

    assert response.status_code == status
    assert "traceback" not in response.text.lower()


def test_core_transport_failure_on_create_renders_503(
    client: TestClient, fake_core: FakeCoreClient
) -> None:
    fake_core.error = CoreUnavailableError()

    response = client.post("/schedule", data=BASE_FORM)

    assert response.status_code == 503
    assert "traceback" not in response.text.lower()


def test_core_transport_failure_on_read_renders_503(
    client: TestClient, fake_core: FakeCoreClient
) -> None:
    fake_core.error = CoreUnavailableError()

    response = client.get("/schedule")

    assert response.status_code == 503
    assert "traceback" not in response.text.lower()


def test_core_five_hundred_maps_to_503(
    client: TestClient, fake_core: FakeCoreClient
) -> None:
    fake_core.error = CoreClientError(500, "internal", "boom")

    response = client.get("/schedule")

    assert response.status_code == 503
    assert "traceback" not in response.text.lower()


def test_cancel_core_failure_renders_safe_error(
    client: TestClient, fake_core: FakeCoreClient
) -> None:
    plan = plan_read()
    fake_core.plans.append(plan)
    fake_core.error = CoreClientError(409, "conflict", "already cancelled")

    response = client.post(f"/schedule/{plan.id}/cancel", follow_redirects=False)

    assert response.status_code == 409
    assert "traceback" not in response.text.lower()


def test_edit_validation_error_preserves_values(
    client: TestClient, fake_core: FakeCoreClient
) -> None:
    plan = plan_read()
    fake_core.plans.append(plan)

    response = client.post(
        f"/schedule/{plan.id}/edit",
        data={
            "title": "Renamed",
            "start_at": "2026-09-20T14:00",
            "end_at": "2026-09-20T10:00",
            "cpu_cores": "abc",
        },
    )

    assert response.status_code == 422
    assert "Renamed" in response.text
    assert "traceback" not in response.text.lower()


def test_edit_core_failure_preserves_values(
    client: TestClient, fake_core: FakeCoreClient
) -> None:
    plan = plan_read()
    fake_core.plans.append(plan)
    fake_core.error = CoreClientError(409, "conflict", "overlaps an existing plan")
    fake_core.fail_at = 1  # get_plan succeeds; update_plan fails

    response = client.post(
        f"/schedule/{plan.id}/edit",
        data={"title": "Renamed", "start_at": "2026-09-20T14:00", "end_at": "2026-09-20T18:00"},
    )

    assert response.status_code == 409
    assert "Renamed" in response.text
    assert "traceback" not in response.text.lower()
