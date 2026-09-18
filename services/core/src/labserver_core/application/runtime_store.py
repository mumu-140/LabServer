import threading
from datetime import datetime

from labserver_contracts.monitoring import FreshnessStatus
from labserver_contracts.runtime import HostRuntimeReport


class RuntimeStore:
    """Thread-safe in-memory store holding the latest runtime report for each server."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._reports: dict[str, HostRuntimeReport] = {}

    def set_report(self, report: HostRuntimeReport) -> None:
        with self._lock:
            self._reports[report.server_key] = report

    def get_report(self, server_key: str) -> HostRuntimeReport | None:
        with self._lock:
            return self._reports.get(server_key)

    def get_freshness(
        self,
        server_key: str,
        now: datetime,
        threshold_seconds: float = 120.0,
    ) -> FreshnessStatus:
        with self._lock:
            report = self._reports.get(server_key)
            if report is None:
                return FreshnessStatus.UNKNOWN
            elapsed = (now - report.reported_at).total_seconds()
            if elapsed <= threshold_seconds:
                return FreshnessStatus.FRESH
            return FreshnessStatus.STALE

    def clear(self) -> None:
        with self._lock:
            self._reports.clear()
