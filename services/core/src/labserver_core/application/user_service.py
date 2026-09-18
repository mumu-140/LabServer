from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from labserver_contracts.users import UserCreate, UserUpdate

from labserver_core.domain.entities import User
from labserver_core.domain.errors import DomainValidationError, NotFound

from .actors import CurrentActor, require_active_actor, require_admin
from .ports import UnitOfWorkFactory


def _utc_now() -> datetime:
    return datetime.now(UTC)


class UserService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        *,
        clock: Callable[[], datetime] = _utc_now,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._id_factory = id_factory

    def list_users(self, actor: CurrentActor) -> list[User]:
        # The planning user directory is member-readable: the shared schedule
        # needs owner display names and owner filters. Mutation stays admin-only.
        with self._uow_factory() as uow:
            require_active_actor(actor, uow.users.get(actor.user_id))
            return uow.users.list_all()

    def create_user(self, actor: CurrentActor, data: UserCreate) -> User:
        with self._uow_factory() as uow:
            require_active_actor(actor, uow.users.get(actor.user_id))
            require_admin(actor)
            if uow.users.get_by_username(data.username) is not None:
                raise DomainValidationError(f"Username {data.username!r} already exists")

            now = self._clock()
            user = User(
                id=self._id_factory(),
                username=data.username,
                display_name=data.display_name,
                role=data.role,
                enabled=data.enabled,
                created_at=now,
                updated_at=now,
            )
            uow.users.add(user)
            uow.commit()
            return user

    def update_user(self, actor: CurrentActor, user_id: UUID, data: UserUpdate) -> User:
        with self._uow_factory() as uow:
            require_active_actor(actor, uow.users.get(actor.user_id))
            require_admin(actor)
            user = uow.users.get(user_id)
            if user is None:
                raise NotFound("User not found")
            if data.enabled is False and user.id == actor.user_id:
                raise DomainValidationError("Cannot disable your own account")

            now = self._clock()
            updated = replace(
                user,
                display_name=data.display_name if data.display_name is not None else user.display_name,
                role=data.role if data.role is not None else user.role,
                enabled=data.enabled if data.enabled is not None else user.enabled,
                updated_at=now,
            )
            uow.users.save(updated)
            uow.commit()
            return updated
