from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from labserver_contracts.auth import LoginRequest, SessionRead

from labserver_core.api.dependencies import get_auth_service, get_current_actor
from labserver_core.application.actors import CurrentActor
from labserver_core.application.auth_service import AuthService
from labserver_core.config import Settings

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=SessionRead)
def login(
    data: LoginRequest,
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> SessionRead:
    ctx = service.login(data.username, data.password)
    settings: Settings = request.app.state.settings
    response.set_cookie(
        key="labserver_session",
        value=ctx.raw_token,
        httponly=True,
        samesite="lax",
        path="/",
        secure=settings.cookie_secure,
    )
    return SessionRead(user_id=ctx.user_id, role=ctx.role)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
    _: Annotated[CurrentActor, Depends(get_current_actor)],
) -> None:
    token = request.cookies.get("labserver_session")
    if token:
        service.logout(token)
    response.delete_cookie(key="labserver_session", path="/")


@router.get("/me", response_model=SessionRead)
def me(
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
) -> SessionRead:
    return SessionRead(user_id=actor.user_id, role=actor.role)
