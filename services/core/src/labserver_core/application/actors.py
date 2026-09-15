from dataclasses import dataclass
from uuid import UUID

from labserver_contracts.common import UserRole

from labserver_core.domain.entities import User
from labserver_core.domain.errors import Forbidden


@dataclass(frozen=True, slots=True)
class CurrentActor:
    user_id: UUID
    role: UserRole


def require_admin(actor: CurrentActor) -> None:
    if actor.role is not UserRole.ADMIN:
        raise Forbidden("Administrator privileges are required")


def require_self_or_admin(actor: CurrentActor, owner_id: UUID) -> None:
    if actor.role is not UserRole.ADMIN and actor.user_id != owner_id:
        raise Forbidden("Actor cannot access another user's resource")


def require_active_actor(actor: CurrentActor, stored_user: User | None) -> User:
    if stored_user is None or not stored_user.enabled:
        raise Forbidden("Current user is unavailable or disabled")
    if stored_user.role is not actor.role:
        raise Forbidden("Current actor role does not match persisted user role")
    return stored_user
