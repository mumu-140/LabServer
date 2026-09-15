from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from labserver_contracts.plans import PlanConflictRead, PlanCreate, PlanRead, PlanUpdate

from labserver_core.api.dependencies import get_current_actor, get_plan_service
from labserver_core.application.actors import CurrentActor
from labserver_core.application.plan_service import PlanService

router = APIRouter(prefix="/plans", tags=["plans"])


def _require_aware(value: datetime | None, name: str) -> datetime | None:
    if value is not None and value.tzinfo is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{name} must include a timezone",
        )
    return value


@router.get("", response_model=list[PlanRead])
def list_plans(
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    service: Annotated[PlanService, Depends(get_plan_service)],
    server_id: Annotated[UUID | None, Query()] = None,
    owner_id: Annotated[UUID | None, Query()] = None,
    start: Annotated[datetime | None, Query()] = None,
    end: Annotated[datetime | None, Query()] = None,
    include_cancelled: bool = False,
) -> list[PlanRead]:
    start = _require_aware(start, "start")
    end = _require_aware(end, "end")
    return service.list(
        actor,
        server_id=server_id,
        owner_id=owner_id,
        start=start,
        end=end,
        include_cancelled=include_cancelled,
    )


@router.post("", response_model=PlanRead, status_code=status.HTTP_201_CREATED)
def create_plan(
    data: PlanCreate,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    service: Annotated[PlanService, Depends(get_plan_service)],
) -> PlanRead:
    return service.create(actor, data)


@router.get("/{plan_id}", response_model=PlanRead)
def get_plan(
    plan_id: UUID,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    service: Annotated[PlanService, Depends(get_plan_service)],
) -> PlanRead:
    return service.get(actor, plan_id)


@router.patch("/{plan_id}", response_model=PlanRead)
def update_plan(
    plan_id: UUID,
    data: PlanUpdate,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    service: Annotated[PlanService, Depends(get_plan_service)],
) -> PlanRead:
    return service.update(actor, plan_id, data)


@router.post("/{plan_id}/cancel", response_model=PlanRead)
def cancel_plan(
    plan_id: UUID,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    service: Annotated[PlanService, Depends(get_plan_service)],
) -> PlanRead:
    return service.cancel(actor, plan_id)


@router.get("/{plan_id}/conflicts", response_model=list[PlanConflictRead])
def list_plan_conflicts(
    plan_id: UUID,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    service: Annotated[PlanService, Depends(get_plan_service)],
) -> list[PlanConflictRead]:
    return service.conflicts(actor, plan_id)
