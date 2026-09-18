from enum import StrEnum
from uuid import UUID

from .common import ReadModel, StrictWriteModel, UtcDateTime
from .monitoring import FreshnessStatus
from .plans import PlanRead


class RuntimeStatus(StrEnum):
    ACTIVE = "active"
    IDLE = "idle"
    UNAVAILABLE = "unavailable"


class RuntimePlanCorrelation(StrEnum):
    MATCHED = "matched"
    UNPLANNED = "unplanned"
    IDLE_RESERVATION = "idle_reservation"


class GpuProcessInfo(ReadModel):
    gpu_id: int
    pid: int
    process_name: str
    username: str
    used_memory_mb: float | None = None
    correlation: RuntimePlanCorrelation = RuntimePlanCorrelation.UNPLANNED
    matched_plan_id: UUID | None = None
    matched_plan_title: str | None = None
    matched_plan_owner: str | None = None


class GpuDeviceRuntime(ReadModel):
    index: int
    name: str
    memory_total_mb: float
    memory_used_mb: float
    utilization_gpu_percent: float | None = None
    temperature_celsius: int | None = None
    processes: list[GpuProcessInfo] = []
    active_plans_count: int = 0


class HostRuntimeReport(StrictWriteModel):
    server_key: str
    reported_at: UtcDateTime
    gpus: list[GpuDeviceRuntime] = []


class HostRuntimeRead(ReadModel):
    server_key: str
    display_name: str
    status: RuntimeStatus
    reported_at: UtcDateTime | None = None
    freshness: FreshnessStatus
    gpus: list[GpuDeviceRuntime] = []
    ongoing_plans: list[PlanRead] = []
    unplanned_processes_count: int = 0


class RuntimeOverviewRead(ReadModel):
    servers: list[HostRuntimeRead]
    observed_at: UtcDateTime
