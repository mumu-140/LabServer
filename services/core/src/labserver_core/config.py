import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            database_url=os.environ.get(
                "LABSERVER_DATABASE_URL", "sqlite:///./labserver.sqlite3"
            )
        )
