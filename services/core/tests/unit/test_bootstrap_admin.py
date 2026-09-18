import io
from pathlib import Path

from alembic import command
from alembic.config import Config
from labserver_contracts.common import UserRole
from labserver_core.application.passwords import Argon2PasswordHasher
from labserver_core.bootstrap_admin import main
from labserver_core.config import Settings
from labserver_core.persistence.database import create_engine_and_session_factory
from labserver_core.persistence.repositories import UserRepository

CORE_DIR = Path(__file__).resolve().parents[2]


def upgrade_database(database_url: str, revision: str = "head") -> None:
    config = Config(str(CORE_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    config.set_main_option("sqlalchemy.isolation_level", "AUTOCOMMIT")
    command.upgrade(config, revision)


def _make_db(tmp_path: Path):
    db_file = tmp_path / "bootstrap.sqlite"
    database_url = f"sqlite:///{db_file}"
    upgrade_database(database_url)
    settings = Settings(database_url=database_url)
    _, session_factory = create_engine_and_session_factory(database_url)
    return settings, session_factory


def test_bootstrap_admin_refuses_when_admin_exists(tmp_path: Path):
    settings, session_factory = _make_db(tmp_path)
    stdout = io.StringIO()
    stderr = io.StringIO()

    # First run succeeds
    ret1 = main(["adminuser"], settings=settings, stdout=stdout, stderr=stderr)
    assert ret1 == 0
    assert "Generated password:" in stdout.getvalue()

    # Second run refuses
    stdout2 = io.StringIO()
    stderr2 = io.StringIO()
    ret2 = main(["anotheradmin"], settings=settings, stdout=stdout2, stderr=stderr2)
    assert ret2 == 1
    assert "enabled administrator already exists" in stderr2.getvalue()


def test_bootstrap_admin_creates_user_and_stores_hash_not_plaintext(tmp_path: Path):
    settings, session_factory = _make_db(tmp_path)
    stdout = io.StringIO()
    stderr = io.StringIO()

    ret = main(["bootstrap_hero"], settings=settings, stdout=stdout, stderr=stderr)
    assert ret == 0

    output = stdout.getvalue()
    lines = [line.strip() for line in output.splitlines() if "Generated password:" in line]
    assert len(lines) == 1
    generated_password = lines[0].split("Generated password:")[-1].strip()
    assert len(generated_password) >= 8

    with session_factory() as session:
        user = UserRepository(session).get_by_username("bootstrap_hero")
        assert user is not None
        assert user.role == UserRole.ADMIN
        assert user.enabled is True
        assert user.password_hash is not None
        assert user.password_hash != generated_password
        hasher = Argon2PasswordHasher()
        assert hasher.verify(generated_password, user.password_hash) is True


def test_bootstrap_admin_promote_existing_user(tmp_path: Path):
    settings, session_factory = _make_db(tmp_path)

    from datetime import UTC, datetime
    from uuid import uuid4

    from labserver_core.domain.entities import User

    now = datetime.now(UTC)
    with session_factory() as session:
        UserRepository(session).add(
            User(
                id=uuid4(),
                username="existing_member",
                display_name="Existing Member",
                role=UserRole.MEMBER,
                enabled=True,
                created_at=now,
                updated_at=now,
                password_hash=None,
            )
        )
        session.commit()

    stdout1 = io.StringIO()
    stderr1 = io.StringIO()
    ret1 = main(["existing_member"], settings=settings, stdout=stdout1, stderr=stderr1)
    assert ret1 == 1
    assert "Pass --promote" in stderr1.getvalue()

    stdout2 = io.StringIO()
    stderr2 = io.StringIO()
    ret2 = main(["existing_member", "--promote"], settings=settings, stdout=stdout2, stderr=stderr2)
    assert ret2 == 0
    lines = [
        line.strip()
        for line in stdout2.getvalue().splitlines()
        if "Generated password:" in line
    ]
    password = lines[0].split("Generated password:")[-1].strip()

    with session_factory() as session:
        user = UserRepository(session).get_by_username("existing_member")
        assert user is not None
        assert user.role == UserRole.ADMIN
        hasher = Argon2PasswordHasher()
        assert hasher.verify(password, user.password_hash) is True
