from datetime import UTC, datetime
from uuid import UUID

import pytest
from labserver_contracts.plans import (
    PlanConflictRead,
    PlanCreate,
    PlanDisplayState,
    PlanRead,
    PlanUpdate,
)
from pydantic import ValidationError

SERVER_ID = "00000000-0000-0000-0000-000000000010"


def test_plan_create_allows_time_only_intent() -> None:
    plan = PlanCreate.model_validate(
        {
            "server_id": SERVER_ID,
            "title": "Poplar assembly",
            "start_at": "2026-09-18T00:00:00Z",
            "end_at": "2026-09-20T00:00:00Z",
        }
    )
    assert plan.server_id == UUID(SERVER_ID)
    assert plan.project is None
    assert plan.cpu_cores is None
    assert plan.memory_gb is None
    assert plan.gpu_count is None
    assert plan.gpu_ids is None
    assert plan.note is None


def test_plan_create_normalizes_to_utc() -> None:
    plan = PlanCreate.model_validate(
        {
            "server_id": SERVER_ID,
            "title": "Training",
            "start_at": "2026-09-18T10:00:00+08:00",
            "end_at": "2026-09-18T12:00:00+08:00",
        }
    )
    assert plan.start_at == datetime(2026, 9, 18, 2, 0, tzinfo=UTC)
    assert plan.end_at == datetime(2026, 9, 18, 4, 0, tzinfo=UTC)
    assert plan.start_at.tzinfo == UTC


def test_plan_create_accepts_optional_resource_intent() -> None:
    plan = PlanCreate.model_validate(
        {
            "server_id": SERVER_ID,
            "title": "Training",
            "project": "poplar",
            "start_at": "2026-09-18T00:00:00Z",
            "end_at": "2026-09-18T06:00:00Z",
            "cpu_cores": 32,
            "memory_gb": 128.0,
            "gpu_count": 2,
            "gpu_ids": [0, 1],
            "note": "shared with Bob",
        }
    )
    assert plan.cpu_cores == 32
    assert plan.memory_gb == 128.0
    assert plan.gpu_count == 2
    assert plan.gpu_ids == (0, 1)


def test_plan_create_rejects_non_positive_interval() -> None:
    for end_at in ("2026-09-18T00:00:00Z", "2026-09-17T23:00:00Z"):
        with pytest.raises(ValidationError):
            PlanCreate.model_validate(
                {
                    "server_id": SERVER_ID,
                    "title": "Training",
                    "start_at": "2026-09-18T00:00:00Z",
                    "end_at": end_at,
                }
            )


def test_plan_create_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError):
        PlanCreate.model_validate(
            {
                "server_id": SERVER_ID,
                "title": "Training",
                "start_at": "2026-09-18T00:00:00",
                "end_at": "2026-09-18T06:00:00",
            }
        )


def test_plan_create_rejects_duplicate_gpu_ids() -> None:
    with pytest.raises(ValidationError):
        PlanCreate.model_validate(
            {
                "server_id": SERVER_ID,
                "title": "Training",
                "start_at": "2026-09-18T00:00:00Z",
                "end_at": "2026-09-18T06:00:00Z",
                "gpu_ids": [0, 0],
            }
        )


def test_plan_create_rejects_negative_gpu_ids() -> None:
    with pytest.raises(ValidationError):
        PlanCreate.model_validate(
            {
                "server_id": SERVER_ID,
                "title": "Training",
                "start_at": "2026-09-18T00:00:00Z",
                "end_at": "2026-09-18T06:00:00Z",
                "gpu_ids": [-1],
            }
        )


def test_plan_create_rejects_gpu_count_mismatch() -> None:
    with pytest.raises(ValidationError):
        PlanCreate.model_validate(
            {
                "server_id": SERVER_ID,
                "title": "Training",
                "start_at": "2026-09-18T00:00:00Z",
                "end_at": "2026-09-18T06:00:00Z",
                "gpu_count": 1,
                "gpu_ids": [0, 1],
            }
        )


def test_plan_create_forbids_unknown_and_owned_fields() -> None:
    for extra in ({"owner_id": SERVER_ID}, {"status": "approved"}, {"approved_at": None}):
        payload = {
            "server_id": SERVER_ID,
            "title": "Training",
            "start_at": "2026-09-18T00:00:00Z",
            "end_at": "2026-09-18T06:00:00Z",
            **extra,
        }
        with pytest.raises(ValidationError):
            PlanCreate.model_validate(payload)


def test_plan_update_allows_partial_mutation() -> None:
    update = PlanUpdate.model_validate({"title": "Renamed"})
    assert update.title == "Renamed"
    assert update.start_at is None
    assert "owner_id" not in PlanUpdate.model_fields


def test_plan_update_validates_interval_when_both_bounds_given() -> None:
    with pytest.raises(ValidationError):
        PlanUpdate.model_validate(
            {"start_at": "2026-09-18T06:00:00Z", "end_at": "2026-09-18T06:00:00Z"}
        )


def test_plan_update_rejects_duplicate_gpu_ids() -> None:
    with pytest.raises(ValidationError):
        PlanUpdate.model_validate({"gpu_ids": [1, 1]})


def test_plan_read_exposes_derived_display_state() -> None:
    plan = PlanRead.model_validate(
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "owner_id": "00000000-0000-0000-0000-000000000002",
            "server_id": SERVER_ID,
            "title": "Training",
            "project": None,
            "start_at": "2026-09-18T00:00:00Z",
            "end_at": "2026-09-18T06:00:00Z",
            "cpu_cores": None,
            "memory_gb": None,
            "gpu_count": None,
            "gpu_ids": None,
            "note": None,
            "cancelled_at": None,
            "created_at": "2026-09-15T00:00:00Z",
            "updated_at": "2026-09-15T00:00:00Z",
            "display_state": "upcoming",
        }
    )
    assert plan.display_state is PlanDisplayState.UPCOMING


def test_plan_display_state_values() -> None:
    assert {state.value for state in PlanDisplayState} == {
        "cancelled",
        "upcoming",
        "ongoing",
        "past",
    }


def test_plan_conflict_read_is_advisory_payload() -> None:
    conflict = PlanConflictRead.model_validate(
        {
            "resource": "gpu_device",
            "certainty": "confirmed",
            "start_at": "2026-09-18T01:00:00Z",
            "end_at": "2026-09-18T02:00:00Z",
            "requested": [0],
            "available": None,
            "conflicting_plan_ids": ["00000000-0000-0000-0000-000000000003"],
            "reason": "GPU 0 already planned",
        }
    )
    assert conflict.conflicting_plan_ids == (
        UUID("00000000-0000-0000-0000-000000000003"),
    )
