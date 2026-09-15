import pytest
from labserver_contracts.common import (
    ConflictCertainty,
    ConflictResource,
    UserRole,
)
from labserver_contracts.plans import (
    PlanConflictRead,
    PlanCreate,
    PlanDisplayState,
    PlanRead,
)
from pydantic import ValidationError


def test_canonical_enum_values_are_stable() -> None:
    assert [item.value for item in UserRole] == ["admin", "member"]
    assert [item.value for item in ConflictCertainty] == ["confirmed", "uncertain"]
    assert [item.value for item in ConflictResource] == [
        "cpu",
        "memory",
        "gpu",
        "gpu_device",
    ]
    assert [item.value for item in PlanDisplayState] == [
        "cancelled",
        "upcoming",
        "ongoing",
        "past",
    ]


def test_plan_create_serializes_to_json_safe_payload() -> None:
    plan = PlanCreate.model_validate(
        {
            "server_id": "00000000-0000-0000-0000-000000000010",
            "title": "Poplar assembly",
            "project": "Populus",
            "start_at": "2026-09-18T08:00:00+08:00",
            "end_at": "2026-09-18T12:00:00+08:00",
            "cpu_cores": 32,
            "memory_gb": 128.0,
            "gpu_count": 2,
            "gpu_ids": [0, 1],
            "note": "HiFi assembly",
        }
    )
    payload = plan.model_dump(mode="json")
    assert payload["start_at"] == "2026-09-18T00:00:00Z"
    assert payload["end_at"] == "2026-09-18T04:00:00Z"
    assert payload["gpu_ids"] == [0, 1]
    assert payload["project"] == "Populus"


def test_plan_create_rejects_invalid_gpu_shapes() -> None:
    base = {
        "server_id": "00000000-0000-0000-0000-000000000010",
        "title": "Training",
        "start_at": "2026-09-18T08:00:00Z",
        "end_at": "2026-09-18T10:00:00Z",
    }
    with pytest.raises(ValidationError):
        PlanCreate.model_validate({**base, "gpu_ids": [1, 1]})
    with pytest.raises(ValidationError):
        PlanCreate.model_validate({**base, "gpu_ids": [-2]})
    with pytest.raises(ValidationError):
        PlanCreate.model_validate({**base, "gpu_count": 3, "gpu_ids": [0, 1]})


def test_plan_read_round_trips_from_mapping() -> None:
    read = PlanRead.model_validate(
        {
            "id": "00000000-0000-0000-0000-000000000011",
            "owner_id": "00000000-0000-0000-0000-000000000012",
            "server_id": "00000000-0000-0000-0000-000000000010",
            "title": "Poplar assembly",
            "project": None,
            "start_at": "2026-09-18T00:00:00Z",
            "end_at": "2026-09-18T04:00:00Z",
            "cpu_cores": None,
            "memory_gb": None,
            "gpu_count": None,
            "gpu_ids": None,
            "note": None,
            "cancelled_at": None,
            "created_at": "2026-09-15T00:00:00Z",
            "updated_at": "2026-09-15T00:00:00Z",
            "display_state": "ongoing",
        }
    )
    assert read.display_state is PlanDisplayState.ONGOING
    assert read.model_dump(mode="json")["display_state"] == "ongoing"


def test_plan_conflict_read_keeps_resource_vocabulary() -> None:
    conflict = PlanConflictRead.model_validate(
        {
            "resource": "memory",
            "certainty": "confirmed",
            "start_at": "2026-09-18T01:00:00Z",
            "end_at": "2026-09-18T02:00:00Z",
            "requested": 128.0,
            "available": 64.0,
            "conflicting_plan_ids": [],
            "reason": "Memory oversubscribed",
        }
    )
    assert conflict.resource is ConflictResource.MEMORY
    assert conflict.certainty is ConflictCertainty.CONFIRMED
