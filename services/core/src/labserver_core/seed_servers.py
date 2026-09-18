import argparse
import sys
from dataclasses import replace
from datetime import UTC, datetime
from typing import TextIO
from uuid import uuid4

from labserver_core.config import Settings
from labserver_core.domain.entities import ManagedServer, ServerCapacity
from labserver_core.persistence.database import create_engine_and_session_factory
from labserver_core.persistence.unit_of_work import SqlAlchemyUnitOfWork

DEFAULT_FLEET_SERVERS: tuple[dict[str, object], ...] = (
    {
        "key": "fwq10",
        "display_name": "fwq10",
        "cpu_cores": 88,
        "memory_gb": 503.0,
        "gpu_count": 0,
    },
    {
        "key": "fwq51",
        "display_name": "fwq51",
        "cpu_cores": 80,
        "memory_gb": 503.0,
        "gpu_count": 1,
    },
    {
        "key": "fwq56",
        "display_name": "fwq56",
        "cpu_cores": 40,
        "memory_gb": 377.0,
        "gpu_count": 0,
    },
    {
        "key": "fwq57",
        "display_name": "fwq57",
        "cpu_cores": 128,
        "memory_gb": 251.0,
        "gpu_count": 4,
    },
)


def seed_servers(
    uow_factory: type[SqlAlchemyUnitOfWork] | type[object] | object,
    servers: tuple[dict[str, object], ...] = DEFAULT_FLEET_SERVERS,
    stdout: TextIO = sys.stdout,
) -> list[ManagedServer]:
    now = datetime.now(UTC)
    seeded: list[ManagedServer] = []

    # uow_factory callable
    factory_fn = uow_factory  # type: ignore[operator]
    with factory_fn() as uow:
        for entry in servers:
            key = str(entry["key"])
            display_name = str(entry["display_name"])
            cpu_cores = int(entry["cpu_cores"]) if entry.get("cpu_cores") is not None else None
            memory_gb = float(entry["memory_gb"]) if entry.get("memory_gb") is not None else None
            gpu_count = int(entry["gpu_count"]) if entry.get("gpu_count") is not None else None

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
