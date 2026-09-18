"""Web harness settings.

Local development must never target real hosts by default; the core base URL
is only configurable through environment configuration. `LABSERVER_TIMEZONE`
is an IANA timezone (development default `UTC`) used to interpret naive form
input and render wall-clock times.
"""

import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_CORE_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEZONE_NAME = "UTC"


@dataclass(frozen=True, slots=True)
class WebSettings:
    core_base_url: str = DEFAULT_CORE_BASE_URL
    timezone_name: str = DEFAULT_TIMEZONE_NAME

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)


def load_settings(env: dict[str, str] | None = None) -> WebSettings:
    environment = env if env is not None else dict(os.environ)
    timezone_name = environment.get("LABSERVER_TIMEZONE", DEFAULT_TIMEZONE_NAME)
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError(f"Invalid LABSERVER_TIMEZONE: {timezone_name!r}") from error
    core_url = (
        environment.get("LABSERVER_CORE_URL")
        or environment.get("LABSERVER_CORE_BASE_URL")
        or DEFAULT_CORE_BASE_URL
    )
    return WebSettings(
        core_base_url=core_url,
        timezone_name=timezone_name,
    )
