import io
from pathlib import Path

from alembic import command
from alembic.config import Config
from labserver_core.config import Settings
from labserver_core.persistence.database import create_engine_and_session_factory
from labserver_core.persistence.repositories import ServerRepository
from labserver_core.seed_servers import main

CORE_DIR = Path(__file__).resolve().parents[2]


def upgrade_database(database_url: str, revision: str = "head") -> None:
    config = Config(str(CORE_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    config.set_main_option("sqlalchemy.isolation_level", "AUTOCOMMIT")
    command.upgrade(config, revision)


def _make_db(tmp_path: Path):
    db_file = tmp_path / "seed_test.sqlite"
    database_url = f"sqlite:///{db_file}"
    upgrade_database(database_url)
    settings = Settings(database_url=database_url)
    _, session_factory = create_engine_and_session_factory(database_url)
    return settings, session_factory


def test_seed_servers_creates_fleet_servers(tmp_path: Path):
    settings, session_factory = _make_db(tmp_path)
    stdout = io.StringIO()
    stderr = io.StringIO()

    ret = main([], settings=settings, stdout=stdout, stderr=stderr)
    assert ret == 0
    assert "Successfully seeded 4 fleet servers." in stdout.getvalue()

    with session_factory() as session:
        repo = ServerRepository(session)
        servers = repo.list_all()
        assert len(servers) == 4
        keys = {s.key for s in servers}
        assert keys == {"fwq10", "fwq51", "fwq56", "fwq57"}

        fwq57 = repo.get_by_key("fwq57")
        assert fwq57 is not None
        assert fwq57.capacity.gpu_count == 4
        assert fwq57.capacity.cpu_cores == 128
        assert fwq57.capacity.memory_gb == 251.0
        assert fwq57.enabled is True

        fwq51 = repo.get_by_key("fwq51")
        assert fwq51 is not None
        assert fwq51.capacity.gpu_count == 1
        assert fwq51.capacity.cpu_cores == 80


def test_seed_servers_idempotent(tmp_path: Path):
    settings, session_factory = _make_db(tmp_path)
    stdout1 = io.StringIO()
    stderr1 = io.StringIO()
    ret1 = main([], settings=settings, stdout=stdout1, stderr=stderr1)
    assert ret1 == 0
    assert "Created server: fwq10" in stdout1.getvalue()

    # Second run should update, not error or duplicate
    stdout2 = io.StringIO()
    stderr2 = io.StringIO()
    ret2 = main([], settings=settings, stdout=stdout2, stderr=stderr2)
    assert ret2 == 0
    assert "Updated server: fwq10" in stdout2.getvalue()
    assert "Successfully seeded 4 fleet servers." in stdout2.getvalue()

    with session_factory() as session:
        repo = ServerRepository(session)
        servers = repo.list_all()
        assert len(servers) == 4
