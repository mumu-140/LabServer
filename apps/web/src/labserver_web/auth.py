"""Presentation identity for the Web surface.

Default-deny: until a future auth adapter overrides the `get_current_viewer`
dependency, every Web route that needs a viewer answers HTTP 401. No headers,
cookies, or query parameters are inspected here; Core remains authoritative
for authorization decisions.
"""

from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException
from labserver_contracts.common import UserRole


@dataclass(frozen=True, slots=True)
class ViewerContext:
    user_id: UUID
    role: UserRole


def get_current_viewer() -> ViewerContext:
    raise HTTPException(status_code=401, detail="Authentication adapter is not configured")
