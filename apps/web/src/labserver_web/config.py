"""Web harness settings.

Local development must never target real hosts by default; the core base URL
is only configurable through environment configuration.
"""

import os
from dataclasses import dataclass

DEFAULT_CORE_BASE_URL = "http://127.0.0.1:8000"


@dataclass(frozen=True, slots=True)
class WebSettings:
    core_base_url: str = DEFAULT_CORE_BASE_URL


def load_settings(env: dict[str, str] | None = None) -> WebSettings:
    environment = env if env is not None else dict(os.environ)
    return WebSettings(
        core_base_url=environment.get("LABSERVER_CORE_URL", DEFAULT_CORE_BASE_URL),
    )
