"""Shared /schedule page: who plans to use which server and when."""

import builtins
import pathlib
from datetime import UTC, datetime
from datetime import date as date_type
from typing import Annotated, Any
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from labserver_contracts.common import UserRole
from labserver_contracts.plans import PlanCreate, PlanRead, PlanUpdate
from pydantic import ValidationError

from labserver_web.auth import ViewerContext, get_current_viewer
from labserver_web.clients.core import CoreClient, CoreClientError
from labserver_web.dependencies import CoreClientDep
from labserver_web.time import (
    format_local_window,
    local_day_bounds,
    parse_local_datetime,
    today_in_zone,
)

router = APIRouter(tags=["schedule"])

ViewerDep = Annotated[ViewerContext, Depends(get_current_viewer)]

TEMPLATES = Jinja2Templates(
    directory=str(pathlib.Path(__file__).resolve().parent.parent / "templates")
)


def _now_utc() -> datetime:
    """The "now" used to resolve an omitted date filter (patched in tests)."""
    return datetime.now(tz=UTC)


def _resource_text(plan: PlanRead) -> str:
    parts: list[str] = []
    if plan.cpu_cores is not None:
        parts.append(f"{plan.cpu_cores} CPU")
    if plan.memory_gb is not None:
        parts.append(f"{plan.memory_gb:g} GB")
    if plan.gpu_ids:
        parts.append("GPU " + ", ".join(str(gpu) for gpu in plan.gpu_ids))
    elif plan.gpu_count is not None:
        parts.append(f"{plan.gpu_count} GPU (count)")
    return " · ".join(parts)


def _can_change(viewer: ViewerContext, plan: PlanRead) -> bool:
    """UX-only helper; Core stays authoritative for authorization."""
    return viewer.role is UserRole.ADMIN or viewer.user_id == plan.owner_id


def _core_error_status(error: CoreClientError) -> int:
    """Map a normalized Core failure to a safe HTTP status for the page."""
    if error.status_code in (401, 403, 404, 409, 422):
        return error.status_code
    if 400 <= error.status_code < 500:
        return 422
    return 503


def _error_page(
    request: Request, message: str, status_code: int
) -> Any:
    return TEMPLATES.TemplateResponse(
        request,
        "schedule/error.html",
        {"request": request, "message": message},
        status_code=status_code,
    )


def _core_error_page(request: Request, error: CoreClientError) -> Any:
    return _error_page(request, error.message, _core_error_status(error))


def _session_cookies(request: Request) -> dict[str, str] | None:
    """Forward the viewer's Core session cookie so Core authorizes the call."""
    token = request.cookies.get("labserver_session")
    return {"labserver_session": token} if token else None


def _schedule_context(
    request: Request,
    core: CoreClient,
    viewer: ViewerContext,
    *,
    server_key: str | None,
    owner_id: UUID | None,
    day: date_type | None,
) -> dict[str, Any]:
    zone: ZoneInfo = request.app.state.settings.timezone
    cookies = _session_cookies(request)

    servers = {item.key: item for item in core.list_servers(cookies=cookies)}
    users = {user.id: user for user in core.list_users(cookies=cookies)}

    if server_key is not None and server_key not in servers:
        raise HTTPException(status_code=422, detail=f"Unknown server key: {server_key}")
    if owner_id is not None and owner_id not in users:
        raise HTTPException(status_code=422, detail=f"Unknown owner: {owner_id}")

    if day is None:
        day = today_in_zone(_now_utc(), zone)
    start, end = local_day_bounds(day, zone)

    plans = core.list_plans(
        server_id=servers[server_key].id if server_key is not None else None,
        owner_id=owner_id,
        start=start,
        end=end,
        cookies=cookies,
    )

    rows: list[dict[str, Any]] = []
    for plan in plans:
        warnings = (
            core.list_conflicts(plan.id, cookies=cookies)
            if plan.cancelled_at is None
            else []
        )
        owner = users.get(plan.owner_id)
        rows.append(
            {
                "plan": plan,
                "owner": owner.display_name if owner else str(plan.owner_id),
                "window": format_local_window(plan.start_at, plan.end_at, zone, day),
                "resources": _resource_text(plan),
                "overlap": bool(warnings),
                "can_change": _can_change(viewer, plan),
            }
        )
    rows.sort(key=lambda row: (row["plan"].server_id, row["plan"].start_at, row["plan"].id))

    if server_key is not None:
        selected = servers[server_key]
        groups: builtins.list[dict[str, Any]] = [
            {
                "server": selected,
                "rows": [row for row in rows if row["plan"].server_id == selected.id],
            }
        ]
    else:
        groups = [
            {
                "server": server_item,
                "rows": [row for row in rows if row["plan"].server_id == server_item.id],
            }
            for server_item in servers.values()
        ]

    return {
        "request": request,
        "viewer": viewer,
        "active_tab": "schedule",
        "groups": groups,
        "server_key": server_key or "",
        "owner_id": str(owner_id) if owner_id else "",
        "date": day.isoformat(),
        "timezone_name": zone.key,
        "servers": [selected] if server_key is not None else list(servers.values()),
        "users": list(users.values()),
        "form": {},
    }


def _parse_date(value: str | None) -> date_type | None:
    if not value:
        return None
    try:
        return date_type.fromisoformat(value)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD") from error


def _optional_int(raw: str | None) -> int | None:
    return int(raw) if raw not in (None, "") else None


def _optional_float(raw: str | None) -> float | None:
    return float(raw) if raw not in (None, "") else None


def _optional_gpu_ids(raw: str | None) -> tuple[int, ...] | None:
    if raw in (None, ""):
        return None
    return tuple(int(item.strip()) for item in raw.split(",") if item.strip())


def _plan_create_from_form(
    *,
    zone: ZoneInfo,
    server_id: UUID,
    title: str,
    start_at: str,
    end_at: str,
    project: str | None,
    cpu_cores: str | None,
    memory_gb: str | None,
    gpu_count: str | None,
    gpu_ids: str | None,
    note: str | None,
) -> PlanCreate:
    return PlanCreate(
        server_id=server_id,
        title=title,
        project=project or None,
        start_at=parse_local_datetime(start_at, zone),
        end_at=parse_local_datetime(end_at, zone),
        cpu_cores=_optional_int(cpu_cores),
        memory_gb=_optional_float(memory_gb),
        gpu_count=_optional_int(gpu_count),
        gpu_ids=_optional_gpu_ids(gpu_ids),
        note=note or None,
    )


def _load_changeable_plan(
    core: CoreClient,
    plan_id: UUID,
    viewer: ViewerContext,
    *,
    cookies: dict[str, str] | None = None,
) -> PlanRead:
    plan = core.get_plan(plan_id, cookies=cookies)
    if not _can_change(viewer, plan):
        raise HTTPException(
            status_code=403,
            detail="Only the plan owner or an admin can change this plan",
        )
    return plan


@router.get("/schedule")
def view_schedule(
    request: Request,
    core: CoreClientDep,
    viewer: ViewerDep,
    server: Annotated[str | None, Query()] = None,
    owner: Annotated[UUID | None, Query()] = None,
    date: Annotated[str | None, Query()] = None,
) -> Any:
    try:
        context = _schedule_context(
            request,
            core,
            viewer,
            server_key=server,
            owner_id=owner,
            day=_parse_date(date),
        )
    except CoreClientError as error:
        return _core_error_page(request, error)
    return TEMPLATES.TemplateResponse(request, "schedule/index.html", context)


@router.get("/schedule/{plan_id}/edit")
def edit_planned_use_form(
    plan_id: UUID, request: Request, core: CoreClientDep, viewer: ViewerDep
) -> Any:
    try:
        plan = _load_changeable_plan(
            core, plan_id, viewer, cookies=_session_cookies(request)
        )
    except CoreClientError as error:
        return _core_error_page(request, error)
    if plan.cancelled_at is not None:
        raise HTTPException(status_code=409, detail="A cancelled plan cannot be edited")
    zone: ZoneInfo = request.app.state.settings.timezone
    return TEMPLATES.TemplateResponse(
        request,
        "schedule/edit.html",
        {
            "request": request,
            "viewer": viewer,
            "active_tab": "schedule",
            "plan": plan,
            "title_value": plan.title,
            "project_value": plan.project or "",
            "start_value": plan.start_at.astimezone(zone).strftime("%Y-%m-%dT%H:%M"),
            "end_value": plan.end_at.astimezone(zone).strftime("%Y-%m-%dT%H:%M"),
            "cpu_value": "" if plan.cpu_cores is None else str(plan.cpu_cores),
            "memory_value": "" if plan.memory_gb is None else str(plan.memory_gb),
            "gpu_count_value": "" if plan.gpu_count is None else str(plan.gpu_count),
            "gpu_ids_value": ",".join(str(gpu) for gpu in plan.gpu_ids) if plan.gpu_ids else "",
            "note_value": plan.note or "",
            "timezone_name": zone.key,
            "form_error": None,
        },
    )


def _edit_form_values(
    title: str,
    start_at: str,
    end_at: str,
    project: str,
    cpu_cores: str,
    memory_gb: str,
    gpu_count: str,
    gpu_ids: str,
    note: str,
) -> dict[str, str]:
    return {
        "title_value": title,
        "project_value": project,
        "start_value": start_at,
        "end_value": end_at,
        "cpu_value": cpu_cores,
        "memory_value": memory_gb,
        "gpu_count_value": gpu_count,
        "gpu_ids_value": gpu_ids,
        "note_value": note,
    }

@router.post("/schedule/{plan_id}/edit")
def edit_planned_use(
    plan_id: UUID,
    request: Request,
    core: CoreClientDep,
    viewer: ViewerDep,
    title: Annotated[str, Form()],
    start_at: Annotated[str, Form()],
    end_at: Annotated[str, Form()],
    project: Annotated[str, Form()] = "",
    cpu_cores: Annotated[str, Form()] = "",
    memory_gb: Annotated[str, Form()] = "",
    gpu_count: Annotated[str, Form()] = "",
    gpu_ids: Annotated[str, Form()] = "",
    note: Annotated[str, Form()] = "",
) -> Any:
    try:
        plan = _load_changeable_plan(
            core, plan_id, viewer, cookies=_session_cookies(request)
        )
    except CoreClientError as error:
        return _core_error_page(request, error)
    if plan.cancelled_at is not None:
        raise HTTPException(status_code=409, detail="A cancelled plan cannot be edited")
    zone: ZoneInfo = request.app.state.settings.timezone
    values = _edit_form_values(
        title, start_at, end_at, project, cpu_cores, memory_gb, gpu_count, gpu_ids, note
    )
    try:
        fields: dict[str, Any] = {
            "title": title,
            "start_at": parse_local_datetime(start_at, zone),
            "end_at": parse_local_datetime(end_at, zone),
        }
        if project:
            fields["project"] = project
        if (cpu := _optional_int(cpu_cores)) is not None:
            fields["cpu_cores"] = cpu
        if (memory := _optional_float(memory_gb)) is not None:
            fields["memory_gb"] = memory
        if (gpu_n := _optional_int(gpu_count)) is not None:
            fields["gpu_count"] = gpu_n
        if (gpu_list := _optional_gpu_ids(gpu_ids)) is not None:
            fields["gpu_ids"] = gpu_list
        if note:
            fields["note"] = note
        data = PlanUpdate(**fields)
    except (ValueError, ValidationError):
        values["form_error"] = "Invalid planned use values."
        return _render_edit_error(request, core, plan, values, 422, viewer=viewer)
    try:
        core.update_plan(plan.id, data, cookies=_session_cookies(request))
    except CoreClientError as error:
        values["form_error"] = error.message
        return _render_edit_error(
            request, core, plan, values, _core_error_status(error), viewer=viewer
        )
    return RedirectResponse(url="/schedule", status_code=303)


def _render_edit_error(
    request: Request,
    core: CoreClient,
    plan: PlanRead,
    values: dict[str, Any],
    status_code: int,
    viewer: ViewerContext | None = None,
) -> Any:
    zone: ZoneInfo = request.app.state.settings.timezone
    context = {
        "request": request,
        "viewer": viewer,
        "active_tab": "schedule",
        "plan": plan,
        "timezone_name": zone.key,
    }
    context.update(values)
    return TEMPLATES.TemplateResponse(
        request, "schedule/edit.html", context, status_code=status_code
    )


@router.post("/schedule")
def create_planned_use(
    request: Request,
    core: CoreClientDep,
    viewer: ViewerDep,
    title: Annotated[str, Form()],
    server_key: Annotated[str, Form()],
    start_at: Annotated[str, Form()],
    end_at: Annotated[str, Form()],
    date: Annotated[str, Form()] = "",
    project: Annotated[str, Form()] = "",
    cpu_cores: Annotated[str, Form()] = "",
    memory_gb: Annotated[str, Form()] = "",
    gpu_count: Annotated[str, Form()] = "",
    gpu_ids: Annotated[str, Form()] = "",
    note: Annotated[str, Form()] = "",
) -> Any:
    zone: ZoneInfo = request.app.state.settings.timezone
    form_values: dict[str, str] = {
        "title": title,
        "server_key": server_key,
        "date": date,
        "start_at": start_at,
        "end_at": end_at,
        "project": project,
        "cpu_cores": cpu_cores,
        "memory_gb": memory_gb,
        "gpu_count": gpu_count,
        "gpu_ids": gpu_ids,
        "note": note,
    }

    def _form_error(message: str, status_code: int) -> Any:
        try:
            context = _schedule_context(
                request,
                core,
                viewer,
                server_key=server_key,
                owner_id=None,
                day=_parse_date(date or None),
            )
        except CoreClientError as render_error:
            return _core_error_page(request, render_error)
        context["form_error"] = message
        context["form"] = form_values
        return TEMPLATES.TemplateResponse(
            request, "schedule/index.html", context, status_code=status_code
        )

    try:
        servers = {
            item.key: item
            for item in core.list_servers(cookies=_session_cookies(request))
        }
    except CoreClientError as error:
        return _core_error_page(request, error)
    server = servers.get(server_key)
    if server is None:
        raise HTTPException(status_code=422, detail=f"Unknown server key: {server_key}")
    try:
        data = _plan_create_from_form(
            zone=zone,
            server_id=server.id,
            title=title,
            start_at=start_at,
            end_at=end_at,
            project=project,
            cpu_cores=cpu_cores,
            memory_gb=memory_gb,
            gpu_count=gpu_count,
            gpu_ids=gpu_ids,
            note=note,
        )
    except (ValueError, ValidationError):
        return _form_error("Invalid planned use values.", 422)
    try:
        core.create_plan(data, cookies=_session_cookies(request))
    except CoreClientError as error:
        return _form_error(error.message, _core_error_status(error))
    return RedirectResponse(url="/schedule", status_code=303)


@router.post("/schedule/{plan_id}/cancel")
def cancel_planned_use(
    plan_id: UUID, request: Request, core: CoreClientDep, viewer: ViewerDep
) -> Any:
    try:
        core.cancel_plan(plan_id, cookies=_session_cookies(request))
    except CoreClientError as error:
        return _core_error_page(request, error)
    return RedirectResponse(url="/schedule", status_code=303)
