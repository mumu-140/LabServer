import json
import os
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    session_ttl_hours: int = 168
    cookie_secure: bool = False
    beszel_enabled: bool = True
    beszel_hub_url: str = "http://127.0.0.1:27090"
    beszel_public_url: str = "https://beszel.yangsen666.cloud"
    beszel_username: str = ""
    beszel_password: str = ""
    beszel_token: str = ""
    beszel_timeout_seconds: float = 5.0
    beszel_cache_ttl_seconds: float = 15.0
    beszel_freshness_threshold_seconds: float = 120.0
    beszel_key_map: dict[str, str] = field(default_factory=dict)
    collector_token: str = ""
    runtime_freshness_threshold_seconds: float = 120.0

    @classmethod
    def from_environment(cls) -> "Settings":
        key_map_raw = os.environ.get("LABSERVER_BESZEL_KEY_MAP", "{}")
        try:
            key_map = json.loads(key_map_raw)
            if not isinstance(key_map, dict):
                key_map = {}
        except Exception:
            key_map = {}

        return cls(
            database_url=os.environ.get(
                "LABSERVER_DATABASE_URL", "sqlite:///./labserver.sqlite3"
            ),
            session_ttl_hours=int(
                os.environ.get("LABSERVER_SESSION_TTL_HOURS", "168")
            ),
            cookie_secure=os.environ.get("LABSERVER_COOKIE_SECURE", "false").lower()
            in ("true", "1", "yes"),
            beszel_enabled=os.environ.get("LABSERVER_BESZEL_ENABLED", "true").lower()
            in ("true", "1", "yes"),
            beszel_hub_url=os.environ.get(
                "LABSERVER_BESZEL_HUB_URL", "http://127.0.0.1:27090"
            ),
            beszel_public_url=os.environ.get(
                "LABSERVER_BESZEL_PUBLIC_URL", "https://beszel.yangsen666.cloud"
            ),
            beszel_username=os.environ.get("LABSERVER_BESZEL_USERNAME", ""),
            beszel_password=os.environ.get("LABSERVER_BESZEL_PASSWORD", ""),
            beszel_token=os.environ.get("LABSERVER_BESZEL_TOKEN", ""),
            beszel_timeout_seconds=float(
                os.environ.get("LABSERVER_BESZEL_TIMEOUT_SECONDS", "5.0")
            ),
            beszel_cache_ttl_seconds=float(
                os.environ.get("LABSERVER_BESZEL_CACHE_TTL_SECONDS", "15.0")
            ),
            beszel_freshness_threshold_seconds=float(
                os.environ.get("LABSERVER_BESZEL_FRESHNESS_THRESHOLD_SECONDS", "120.0")
            ),
            beszel_key_map=key_map,
            collector_token=os.environ.get("LABSERVER_COLLECTOR_TOKEN", ""),
            runtime_freshness_threshold_seconds=float(
                os.environ.get("LABSERVER_RUNTIME_FRESHNESS_THRESHOLD_SECONDS", "120.0")
            ),
        )

