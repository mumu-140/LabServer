"""Presentation identity for the Web surface.

Default-deny: every Web route requiring a viewer checks `get_current_viewer`.
Reads the `labserver_session` cookie and resolves it through Core `GET /api/v1/auth/me`.
Any failure raises HTTP 401. Core remains authoritative for authorization decisions.
"""

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from labserver_contracts.common import UserRole

from labserver_web.clients.core import CoreClient, CoreClientError
from labserver_web.dependencies import get_core_client


@dataclass(frozen=True, slots=True)
class ViewerContext:
    user_id: UUID
    role: UserRole


def get_current_viewer(
    request: Request,
    core_client: Annotated[CoreClient, Depends(get_core_client)],
) -> ViewerContext:
    token = request.cookies.get("labserver_session")
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        session = core_client.me(cookies={"labserver_session": token})
        return ViewerContext(user_id=session.user_id, role=session.role)
    except CoreClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
