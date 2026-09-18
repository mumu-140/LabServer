import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    session_ttl_hours: int = 168
    cookie_secure: bool = False

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            database_url=os.environ.get(
                "LABSERVER_DATABASE_URL", "sqlite:///./labserver.sqlite3"
            ),
            session_ttl_hours=int(
                os.environ.get("LABSERVER_SESSION_TTL_HOURS", "168")
            ),
            cookie_secure=os.environ.get("LABSERVER_COOKIE_SECURE", "false").lower()
            in ("true", "1", "yes"),
        )
