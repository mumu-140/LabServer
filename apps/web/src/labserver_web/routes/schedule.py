"""Shared /schedule page: who plans to use which server and when."""

import builtins
import pathlib
from datetime import UTC, datetime
from datetime import date as date_type
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from labserver_contracts.plans import PlanCreate, PlanRead

from labserver_web.clients.core import CoreClient, CoreClientError
from labserver_web.dependencies import CoreClientDep
from labserver_web.time import (
    format_local_window,
    local_day_bounds,
    today_in_zone,
)

router = APIRouter(tags=["schedule"])

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


def _schedule_context(
    request: Request,
    core: CoreClient,
    *,
    server_key: str | None,
    owner_id: UUID | None,
    day: date_type | None,
) -> dict[str, Any]:
    zone = request.app.state.settings.timezone

    servers = {item.key: item for item in core.list_servers()}
    users = {user.id: user for user in core.list_users()}

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
    )

    rows: list[dict[str, Any]] = []
    for plan in plans:
        warnings = core.list_conflicts(plan.id) if plan.cancelled_at is None else []
        owner = users.get(plan.owner_id)
        rows.append(
            {
                "plan": plan,
                "owner": owner.display_name if owner else str(plan.owner_id),
                "window": format_local_window(plan.start_at, plan.end_at, zone, day),
                "resources": _resource_text(plan),
                "overlap": bool(warnings),
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
        "groups": groups,
        "server_key": server_key or "",
        "owner_id": str(owner_id) if owner_id else "",
        "date": day.isoformat(),
        "timezone_name": zone.key,
        "servers": [selected] if server_key is not None else list(servers.values()),
        "users": list(users.values()),
    }


def _parse_date(value: str | None) -> date_type | None:
    if not value:
        return None
    try:
        return date_type.fromisoformat(value)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD") from error


@router.get("/schedule")
def view_schedule(
    request: Request,
    core: CoreClientDep,
    server: Annotated[str | None, Query()] = None,
    owner: Annotated[UUID | None, Query()] = None,
    date: Annotated[str | None, Query()] = None,
) -> Any:
    context = _schedule_context(
        request, core, server_key=server, owner_id=owner, day=_parse_date(date)
    )
    return TEMPLATES.TemplateResponse(request, "schedule/index.html", context)


def _plan_create_from_form(
    *,
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
    def _moment(raw: str) -> datetime:
        stamp = datetime.fromisoformat(raw)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=UTC)
        return stamp

    def _optional_int(raw: str | None) -> int | None:
        return int(raw) if raw not in (None, "") else None

    def _optional_float(raw: str | None) -> float | None:
        return float(raw) if raw not in (None, "") else None

    gpu_list: tuple[int, ...] | None = None
    if gpu_ids not in (None, ""):
        gpu_list = tuple(int(item.strip()) for item in gpu_ids.split(",") if item.strip())

    return PlanCreate(
        server_id=server_id,
        title=title,
        project=project or None,
        start_at=_moment(start_at),
        end_at=_moment(end_at),
        cpu_cores=_optional_int(cpu_cores),
        memory_gb=_optional_float(memory_gb),
        gpu_count=_optional_int(gpu_count),
        gpu_ids=gpu_list,
        note=note or None,
    )


@router.post("/schedule")
def create_planned_use(
    request: Request,
    core: CoreClientDep,
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
    servers = {item.key: item for item in core.list_servers()}
    server = servers.get(server_key)
    if server is None:
        raise HTTPException(status_code=422, detail=f"Unknown server key: {server_key}")
    try:
        data = _plan_create_from_form(
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
        core.create_plan(data)
    except CoreClientError as error:
        context = _schedule_context(
            request,
            core,
            server_key=server_key,
            owner_id=None,
            day=_parse_date(date or None),
        )
        context["form_error"] = error.message
        return TEMPLATES.TemplateResponse(
            request, "schedule/index.html", context, status_code=200
        )
    return RedirectResponse(url="/schedule", status_code=303)


@router.post("/schedule/{plan_id}/cancel")
def cancel_planned_use(plan_id: UUID, request: Request, core: CoreClientDep) -> Any:
    core.cancel_plan(plan_id)
    return RedirectResponse(url="/schedule", status_code=303)
