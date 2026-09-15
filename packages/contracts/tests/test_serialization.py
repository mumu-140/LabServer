from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from labserver_contracts.common import (
    ConflictCertainty,
    ConflictResource,
    ReservationSource,
    ReservationStatus,
    TaskRequestStatus,
    UserRole,
)
from labserver_contracts.requests import TaskRequestCreate, TaskRequestUpdate
from labserver_contracts.servers import ServerCreate
from labserver_contracts.users import UserCreate
from pydantic import ValidationError


def valid_request_payload() -> dict[str, object]:
    return {
        "title": "Poplar assembly",
        "project": "Populus",
        "preferred_server_id": "00000000-0000-0000-0000-000000000010",
        "planned_start": "2026-09-18T08:00:00+08:00",
        "planned_duration_minutes": 2880,
        "requested_cpu_cores": 32,
        "requested_memory_gb": 128.0,
        "requested_gpu_count": 2,
        "preferred_gpu_ids": [0, 1],
        "note": "HiFi assembly",
    }


def test_canonical_enum_values_are_stable() -> None:
    assert [item.value for item in UserRole] == ["admin", "member"]
    assert [item.value for item in TaskRequestStatus] == [
        "draft",
        "submitted",
        "approved",
        "rejected",
        "cancelled",
    ]
    assert [item.value for item in ReservationStatus] == [
        "planned",
        "active",
        "completed",
        "cancelled",
    ]
    assert [item.value for item in ReservationSource] == ["request", "admin"]
    assert [item.value for item in ConflictCertainty] == ["confirmed", "uncertain"]
    assert [item.value for item in ConflictResource] == [
        "cpu",
        "memory",
        "gpu",
        "gpu_device",
    ]


def test_task_request_contract_normalizes_utc() -> None:
    model = TaskRequestCreate.model_validate(valid_request_payload())

    assert model.preferred_server_id == UUID("00000000-0000-0000-0000-000000000010")
    assert model.preferred_gpu_ids == [0, 1]
    assert model.planned_start == datetime(2026, 9, 18, 0, 0, tzinfo=UTC)
    assert model.planned_start.utcoffset() == timedelta(0)
    assert model.model_dump(mode="json")["preferred_server_id"] == (
        "00000000-0000-0000-0000-000000000010"
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("planned_duration_minutes", 0),
        ("requested_cpu_cores", -1),
        ("requested_memory_gb", -0.1),
        ("requested_gpu_count", -1),
        ("preferred_gpu_ids", [-1, 0]),
        ("preferred_gpu_ids", [0, 0]),
    ],
)
def test_task_request_rejects_invalid_resource_values(field: str, value: object) -> None:
    payload = valid_request_payload()
    payload[field] = value

    with pytest.raises(ValidationError):
        TaskRequestCreate.model_validate(payload)


def test_task_request_rejects_naive_datetime() -> None:
    payload = valid_request_payload()
    payload["planned_start"] = "2026-09-18T08:00:00"

    with pytest.raises(ValidationError):
        TaskRequestCreate.model_validate(payload)


def test_task_request_rejects_gpu_count_mismatch() -> None:
    payload = valid_request_payload()
    payload["requested_gpu_count"] = 1

    with pytest.raises(ValidationError):
        TaskRequestCreate.model_validate(payload)


def test_task_request_trims_title_and_rejects_blank_title() -> None:
    payload = valid_request_payload()
    payload["title"] = "  Poplar assembly  "
    model = TaskRequestCreate.model_validate(payload)
    assert model.title == "Poplar assembly"

    payload["title"] = "   "
    with pytest.raises(ValidationError):
        TaskRequestCreate.model_validate(payload)


def test_write_contracts_forbid_unknown_fields_and_server_ip() -> None:
    payload = valid_request_payload()
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        TaskRequestCreate.model_validate(payload)

    with pytest.raises(ValidationError):
        ServerCreate.model_validate(
            {
                "key": "fwq10",
                "display_name": "fwq10",
                "ip": "192.0.2.10",
            }
        )


def test_partial_request_update_only_checks_local_gpu_consistency() -> None:
    update = TaskRequestUpdate.model_validate({"preferred_gpu_ids": [2, 3]})
    assert update.preferred_gpu_ids == [2, 3]

    with pytest.raises(ValidationError):
        TaskRequestUpdate.model_validate(
            {"requested_gpu_count": 1, "preferred_gpu_ids": [2, 3]}
        )


def test_user_create_normalizes_text_and_forbids_extra_fields() -> None:
    user = UserCreate.model_validate(
        {"username": "  alice  ", "display_name": "  Alice Chen  ", "role": "member"}
    )
    assert user.username == "alice"
    assert user.display_name == "Alice Chen"

    with pytest.raises(ValidationError):
        UserCreate.model_validate(
            {
                "username": "alice",
                "display_name": "Alice",
                "role": "member",
                "password": "must-not-be-in-this-contract",
            }
        )
