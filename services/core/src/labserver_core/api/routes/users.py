from typing import Annotated

from fastapi import APIRouter, Depends, status
from labserver_contracts.users import UserCreate, UserRead

from labserver_core.api.dependencies import get_current_actor, get_user_service
from labserver_core.application.actors import CurrentActor
from labserver_core.application.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserRead])
def list_users(
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    service: Annotated[UserService, Depends(get_user_service)],
) -> list[UserRead]:
    return [UserRead.model_validate(item) for item in service.list_users(actor)]


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    data: UserCreate,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserRead:
    return UserRead.model_validate(service.create_user(actor, data))
