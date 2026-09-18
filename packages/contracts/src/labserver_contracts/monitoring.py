from enum import StrEnum

from .common import ReadModel, UtcDateTime
from .plans import PlanRead
from .servers import ServerRead


class HostStatus(StrEnum):
    UP = "up"
    DOWN = "down"
    UNKNOWN = "unknown"


class FreshnessStatus(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    UNREACHABLE = "unreachable"
    DISABLED = "disabled"
    UNKNOWN = "unknown"


class GpuMetricsRead(ReadModel):
    index: int
    name: str | None = None
    utilization_percent: float | None = None
    memory_used_gb: float | None = None
    memory_total_gb: float | None = None
    temperature_c: int | None = None


class HostMetricsRead(ReadModel):
    server_key: str
    status: HostStatus
    freshness: FreshnessStatus
    cpu_percent: float | None = None
    memory_used_gb: float | None = None
    memory_total_gb: float | None = None
    memory_percent: float | None = None
    disk_used_gb: float | None = None
    disk_total_gb: float | None = None
    disk_percent: float | None = None
    load_average: tuple[float, float, float] | None = None
    uptime_seconds: int | None = None
    gpus: list[GpuMetricsRead] | None = None
    upstream_url: str | None = None
    updated_at: UtcDateTime | None = None
    error_message: str | None = None


class ServerDashboardCard(ReadModel):
    server: ServerRead
    metrics: HostMetricsRead | None = None
    active_plans_count: int = 0
    near_term_plans: list[PlanRead] = []


class DashboardRead(ReadModel):
    cards: list[ServerDashboardCard]
    observed_at: UtcDateTime
