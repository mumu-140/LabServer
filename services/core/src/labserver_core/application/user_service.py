from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from labserver_contracts.users import UserCreate

from labserver_core.domain.entities import User
from labserver_core.domain.errors import DomainValidationError

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
        with self._uow_factory() as uow:
            require_active_actor(actor, uow.users.get(actor.user_id))
            require_admin(actor)
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
