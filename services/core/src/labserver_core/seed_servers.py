import argparse
import sys
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TextIO
from uuid import uuid4

from labserver_core.application.ports import UnitOfWorkFactory
from labserver_core.config import Settings
from labserver_core.domain.entities import ManagedServer, ServerCapacity
from labserver_core.persistence.database import create_engine_and_session_factory
from labserver_core.persistence.unit_of_work import SqlAlchemyUnitOfWork


@dataclass(frozen=True, slots=True)
class FleetServerDef:
    key: str
    display_name: str
    cpu_cores: int | None
    memory_gb: float | None
    gpu_count: int | None


DEFAULT_FLEET_SERVERS: tuple[FleetServerDef, ...] = (
    FleetServerDef(
        key="fwq10",
        display_name="fwq10",
        cpu_cores=88,
        memory_gb=503.0,
        gpu_count=0,
    ),
    FleetServerDef(
        key="fwq51",
        display_name="fwq51",
        cpu_cores=80,
        memory_gb=503.0,
        gpu_count=1,
    ),
    FleetServerDef(
        key="fwq56",
        display_name="fwq56",
        cpu_cores=40,
        memory_gb=377.0,
        gpu_count=0,
    ),
    FleetServerDef(
        key="fwq57",
        display_name="fwq57",
        cpu_cores=128,
        memory_gb=251.0,
        gpu_count=4,
    ),
)


def seed_servers(
    uow_factory: UnitOfWorkFactory,
    servers: tuple[FleetServerDef, ...] = DEFAULT_FLEET_SERVERS,
    stdout: TextIO = sys.stdout,
) -> list[ManagedServer]:
    now = datetime.now(UTC)
    seeded: list[ManagedServer] = []

    with uow_factory() as uow:
        for entry in servers:
            key = entry.key
            display_name = entry.display_name
            cpu_cores = entry.cpu_cores
            memory_gb = entry.memory_gb
            gpu_count = entry.gpu_count

            existing = uow.servers.get_by_key(key)
            if existing is not None:
                updated = replace(
                    existing,
                    display_name=display_name,
                    capacity=ServerCapacity(
                        cpu_cores=cpu_cores,
                        memory_gb=memory_gb,
                        gpu_count=gpu_count,
                    ),
                    updated_at=now,
                )
                uow.servers.save(updated)
                seeded.append(updated)
                stdout.write(f"Updated server: {key} ({display_name})\n")
            else:
                new_server = ManagedServer(
                    id=uuid4(),
                    key=key,
                    display_name=display_name,
                    enabled=True,
                    capacity=ServerCapacity(
                        cpu_cores=cpu_cores,
                        memory_gb=memory_gb,
                        gpu_count=gpu_count,
                    ),
                    created_at=now,
                    updated_at=now,
                )
                uow.servers.add(new_server)
                seeded.append(new_server)
                stdout.write(f"Created server: {key} ({display_name})\n")
        uow.commit()

    return seeded


def main(
    argv: list[str] | None = None,
    settings: Settings | None = None,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    parser = argparse.ArgumentParser(
        prog="labserver_core.seed_servers",
        description="Seed or update default fleet servers (fwq10, fwq51, fwq56, fwq57).",
    )
    parser.parse_args(argv)

    resolved_settings = settings or Settings.from_environment()
    _, session_factory = create_engine_and_session_factory(resolved_settings.database_url)

    def uow_factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    try:
        seeded = seed_servers(uow_factory, stdout=stdout)
        stdout.write(f"Successfully seeded {len(seeded)} fleet servers.\n")
        return 0
    except Exception as exc:  # noqa: BLE001
        stderr.write(f"Error seeding fleet servers: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
