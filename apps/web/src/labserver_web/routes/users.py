"""Admin user management route."""

import pathlib
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from labserver_contracts.common import UserRole
from labserver_contracts.users import UserCreate, UserUpdate
from pydantic import ValidationError

from labserver_web.auth import ViewerContext, get_current_viewer
from labserver_web.clients.core import CoreClientError
from labserver_web.dependencies import CoreClientDep

router = APIRouter(prefix="/users", tags=["users"])

TEMPLATES = Jinja2Templates(
    directory=str(pathlib.Path(__file__).resolve().parent.parent / "templates")
)


def require_admin_viewer(
    viewer: Annotated[ViewerContext, Depends(get_current_viewer)],
) -> ViewerContext:
    if viewer.role is not UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Forbidden: Admin access required")
    return viewer


AdminDep = Annotated[ViewerContext, Depends(require_admin_viewer)]


def _get_cookies(request: Request) -> dict[str, str] | None:
    token = request.cookies.get("labserver_session")
    return {"labserver_session": token} if token else None


@router.get("")
def list_users(
    request: Request,
    core: CoreClientDep,
    viewer: AdminDep,
    msg: str | None = Query(default=None),
    err: str | None = Query(default=None),
) -> Any:
    cookies = _get_cookies(request)
    try:
        users = core.list_users(cookies=cookies)
    except CoreClientError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error

    return TEMPLATES.TemplateResponse(
        request,
        "users/index.html",
        {
            "request": request,
            "viewer": viewer,
            "users": users,
            "active_tab": "users",
            "success_message": msg,
            "error_message": err,
        },
    )


@router.post("")
def provision_user(
    request: Request,
    core: CoreClientDep,
    viewer: AdminDep,
    username: Annotated[str, Form()] = "",
    display_name: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
    role: Annotated[str, Form()] = "member",
) -> Any:
    cookies = _get_cookies(request)
    username = username.strip()
    display_name = display_name.strip()

    if not username or not display_name:
        return _render_users_with_error(
            request, core, viewer, "Username and display name cannot be empty."
        )

    if len(password) < 8:
        return _render_users_with_error(
            request, core, viewer, "Password must be at least 8 characters long."
        )

    try:
        user_role = UserRole(role.lower())
    except ValueError:
        return _render_users_with_error(
            request, core, viewer, f"Invalid role: {role}. Must be 'member' or 'admin'."
        )

    try:
        create_payload = UserCreate(
            username=username,
            display_name=display_name,
            role=user_role,
            enabled=True,
        )
        new_user = core.create_user(create_payload, cookies=cookies)
        core.set_user_password(new_user.id, password, cookies=cookies)
    except (ValidationError, CoreClientError) as exc:
        msg = exc.message if isinstance(exc, CoreClientError) else str(exc)
        return _render_users_with_error(request, core, viewer, msg)

    return RedirectResponse(
        url="/users?msg=Member+provisioned+successfully", status_code=303
    )


@router.post("/{user_id}/password")
def reset_password(
    request: Request,
    user_id: UUID,
    core: CoreClientDep,
    viewer: AdminDep,
    password: Annotated[str, Form()] = "",
) -> Any:
    cookies = _get_cookies(request)
    if len(password) < 8:
        return _render_users_with_error(
            request, core, viewer, "Password must be at least 8 characters long."
        )

    try:
        core.set_user_password(user_id, password, cookies=cookies)
    except CoreClientError as exc:
        return _render_users_with_error(request, core, viewer, exc.message)

    return RedirectResponse(
        url="/users?msg=Password+updated+successfully", status_code=303
    )


@router.post("/{user_id}/toggle")
def toggle_user_status(
    request: Request,
    user_id: UUID,
    core: CoreClientDep,
    viewer: AdminDep,
    enabled: Annotated[str, Form()] = "",
) -> Any:
    cookies = _get_cookies(request)
    is_enabled = enabled.lower() in ("true", "1", "yes")

    if not is_enabled and user_id == viewer.user_id:
        return _render_users_with_error(
            request, core, viewer, "Cannot disable your own account."
        )

    try:
        core.update_user(user_id, UserUpdate(enabled=is_enabled), cookies=cookies)
    except CoreClientError as exc:
        return _render_users_with_error(request, core, viewer, exc.message)

    action_text = "enabled" if is_enabled else "disabled"
    return RedirectResponse(
        url=f"/users?msg=User+{action_text}+successfully", status_code=303
    )


def _render_users_with_error(
    request: Request,
    core: CoreClientDep,
    viewer: ViewerContext,
    error_message: str,
    status_code: int = 422,
) -> Any:
    cookies = _get_cookies(request)
    try:
        users = core.list_users(cookies=cookies)
    except Exception:
        users = []

    return TEMPLATES.TemplateResponse(
        request,
        "users/index.html",
        {
            "request": request,
            "viewer": viewer,
            "users": users,
            "active_tab": "users",
            "error_message": error_message,
        },
        status_code=status_code,
    )
