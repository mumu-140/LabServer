import argparse
import secrets
import sys
from dataclasses import replace
from datetime import UTC, datetime
from typing import TextIO
from uuid import uuid4

from labserver_contracts.common import UserRole

from labserver_core.application.auth_service import AuthService
from labserver_core.application.passwords import Argon2PasswordHasher
from labserver_core.config import Settings
from labserver_core.domain.entities import User
from labserver_core.persistence.database import create_engine_and_session_factory
from labserver_core.persistence.unit_of_work import SqlAlchemyUnitOfWork


def main(
    argv: list[str] | None = None,
    settings: Settings | None = None,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    parser = argparse.ArgumentParser(
        prog="labserver_core.bootstrap_admin",
        description="Bootstrap an initial administrator user.",
    )
    parser.add_argument("username", help="Username for the administrator")
    parser.add_argument(
        "--promote",
        action="store_true",
        help="Promote an existing user to admin if they already exist",
    )
    args = parser.parse_args(argv)

    resolved_settings = settings or Settings.from_environment()
    _, session_factory = create_engine_and_session_factory(resolved_settings.database_url)

    def uow_factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    hasher = Argon2PasswordHasher()
    auth_service = AuthService(uow_factory, hasher, resolved_settings)

    if auth_service.has_enabled_admin():
        stderr.write("Error: An enabled administrator already exists. Bootstrap is refused.\n")
        return 1

    password = secrets.token_urlsafe(16)
    password_hash = hasher.hash(password)
    now = datetime.now(UTC)

    with uow_factory() as uow:
        existing = uow.users.get_by_username(args.username)
        if existing is not None:
            if not args.promote:
                stderr.write(
                    f"Error: User {args.username!r} already exists. "
                    "Pass --promote to promote to admin.\n"
                )
                return 1
            promoted = replace(
                existing,
                role=UserRole.ADMIN,
                enabled=True,
                password_hash=password_hash,
                updated_at=now,
            )
            uow.users.save(promoted)
        else:
            new_user = User(
                id=uuid4(),
                username=args.username,
                display_name=args.username,
                role=UserRole.ADMIN,
                enabled=True,
                created_at=now,
                updated_at=now,
                password_hash=password_hash,
            )
            uow.users.add(new_user)
        uow.commit()

    stdout.write(f"Administrator {args.username} bootstrapped successfully.\n")
    stdout.write(f"Generated password: {password}\n")
    stdout.write(
        "Note: Save this password immediately. "
        "It is printed once and will never be shown again.\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
