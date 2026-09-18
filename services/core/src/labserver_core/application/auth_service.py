import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from labserver_contracts.common import UserRole

from labserver_core.config import Settings
from labserver_core.domain.entities import AuthSession
from labserver_core.domain.errors import Forbidden, NotFound, UnknownCredentials

from .actors import CurrentActor, require_active_actor, require_admin
from .passwords import PasswordHasher
from .ports import UnitOfWorkFactory


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _token_generator() -> str:
    return secrets.token_urlsafe(32)


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SessionContext:
    raw_token: str
    user_id: UUID
    role: UserRole


class AuthService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        hasher: PasswordHasher,
        settings: Settings,
        *,
        clock: Callable[[], datetime] = _utc_now,
        token_factory: Callable[[], str] = _token_generator,
    ) -> None:
        self._uow_factory = uow_factory
        self._hasher = hasher
        self._settings = settings
        self._clock = clock
        self._token_factory = token_factory

    def login(self, username: str, password: str) -> SessionContext:
        with self._uow_factory() as uow:
            user = uow.users.get_by_username(username)
            if (
                user is None
                or not user.enabled
                or user.password_hash is None
                or not self._hasher.verify(password, user.password_hash)
            ):
                raise UnknownCredentials("Invalid username or password")

            raw_token = self._token_factory()
            token_hash = _hash_token(raw_token)
            now = self._clock()
            expires_at = now + timedelta(hours=self._settings.session_ttl_hours)

            session_record = AuthSession(
                token_hash=token_hash,
                user_id=user.id,
                created_at=now,
                expires_at=expires_at,
            )
            uow.auth_sessions.add(session_record)
            uow.commit()

            return SessionContext(
                raw_token=raw_token,
                user_id=user.id,
                role=user.role,
            )

    def resolve(self, raw_token: str) -> CurrentActor:
        with self._uow_factory() as uow:
            token_hash = _hash_token(raw_token)
            session_record = uow.auth_sessions.get(token_hash)
            if session_record is None:
                raise UnknownCredentials("Session is invalid or expired")

            now = self._clock()
            if session_record.expires_at <= now:
                uow.auth_sessions.delete(token_hash)
                uow.commit()
                raise UnknownCredentials("Session is invalid or expired")

            stored_user = uow.users.get(session_record.user_id)
            if stored_user is None or not stored_user.enabled:
                raise Forbidden("Current user is unavailable or disabled")

            actor = CurrentActor(user_id=stored_user.id, role=stored_user.role)
            require_active_actor(actor, stored_user)
            return actor

    def logout(self, raw_token: str) -> None:
        with self._uow_factory() as uow:
            token_hash = _hash_token(raw_token)
            uow.auth_sessions.delete(token_hash)
            uow.commit()

    def has_enabled_admin(self) -> bool:
        with self._uow_factory() as uow:
            users = uow.users.list_all()
            return any(u.enabled and u.role is UserRole.ADMIN for u in users)

    def set_password(self, actor: CurrentActor, user_id: UUID, raw: str) -> None:
        with self._uow_factory() as uow:
            require_active_actor(actor, uow.users.get(actor.user_id))
            require_admin(actor)

            target = uow.users.get(user_id)
            if target is None:
                raise NotFound(f"User {user_id} does not exist")

            password_hash = self._hasher.hash(raw)
            uow.users.set_password_hash(user_id, password_hash)
            uow.commit()
