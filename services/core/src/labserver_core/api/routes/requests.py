from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from labserver_contracts.requests import TaskRequestCreate, TaskRequestRead, TaskRequestUpdate
from labserver_contracts.reservations import ConflictRead, ReservationRead

from labserver_core.api.dependencies import get_current_actor, get_request_service
from labserver_core.application.actors import CurrentActor
from labserver_core.application.request_service import RequestService

router = APIRouter(prefix="/requests", tags=["requests"])


def _request_read(item: object) -> TaskRequestRead:
    return TaskRequestRead.model_validate(item)


@router.get("", response_model=list[TaskRequestRead])
def list_requests(
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    service: Annotated[RequestService, Depends(get_request_service)],
) -> list[TaskRequestRead]:
    return [_request_read(item) for item in service.list_requests(actor)]


@router.get("/{request_id}", response_model=TaskRequestRead)
def get_request(
    request_id: UUID,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    service: Annotated[RequestService, Depends(get_request_service)],
) -> TaskRequestRead:
    return _request_read(service.get_request(actor, request_id))


@router.post("", response_model=TaskRequestRead, status_code=status.HTTP_201_CREATED)
def create_request(
    data: TaskRequestCreate,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    service: Annotated[RequestService, Depends(get_request_service)],
) -> TaskRequestRead:
    return _request_read(service.create_request(actor, data))


@router.patch("/{request_id}", response_model=TaskRequestRead)
def update_request(
    request_id: UUID,
    data: TaskRequestUpdate,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    service: Annotated[RequestService, Depends(get_request_service)],
) -> TaskRequestRead:
    return _request_read(service.update_draft(actor, request_id, data))


@router.post("/{request_id}/submit", response_model=TaskRequestRead)
def submit_request(
    request_id: UUID,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    service: Annotated[RequestService, Depends(get_request_service)],
) -> TaskRequestRead:
    return _request_read(service.submit_request(actor, request_id))


@router.post("/{request_id}/cancel", response_model=TaskRequestRead)
def cancel_request(
    request_id: UUID,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    service: Annotated[RequestService, Depends(get_request_service)],
) -> TaskRequestRead:
    return _request_read(service.cancel_request(actor, request_id))


@router.post("/{request_id}/approve", response_model=ReservationRead)
def approve_request(
    request_id: UUID,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    service: Annotated[RequestService, Depends(get_request_service)],
) -> ReservationRead:
    return ReservationRead.model_validate(service.approve_request(actor, request_id))


@router.post("/{request_id}/reject", response_model=TaskRequestRead)
def reject_request(
    request_id: UUID,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    service: Annotated[RequestService, Depends(get_request_service)],
) -> TaskRequestRead:
    return _request_read(service.reject_request(actor, request_id))


@router.get("/{request_id}/conflicts", response_model=list[ConflictRead])
def preview_conflicts(
    request_id: UUID,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    service: Annotated[RequestService, Depends(get_request_service)],
) -> list[ConflictRead]:
    return [
        ConflictRead.model_validate(item)
        for item in service.preview_request_conflicts(actor, request_id)
    ]
