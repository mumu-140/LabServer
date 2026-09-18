import asyncio
import contextlib
import logging
import time
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx
from labserver_contracts.monitoring import (
    FreshnessStatus,
    HostMetricsRead,
    HostStatus,
)

logger = logging.getLogger(__name__)


def _parse_utc_datetime(raw: str) -> datetime:
    normalized = raw.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class HostMetricsProvider(Protocol):
    async def get_metrics(
        self,
        server_keys: list[str],
        server_capacities: dict[str, tuple[float | None, int | None]] | None = None,
    ) -> dict[str, HostMetricsRead]:
        """Fetch metrics for given logical server keys.

        server_capacities: optional mapping of server_key -> (memory_gb, cpu_cores).
        """
        ...

    async def get_server_metrics(
        self,
        server_key: str,
        memory_gb: float | None = None,
        cpu_cores: int | None = None,
    ) -> HostMetricsRead:
        """Fetch metrics for a single server key."""
        ...


class FakeHostMetricsProvider:
    """In-memory test double for zero-network testing."""

    def __init__(self, metrics: dict[str, HostMetricsRead] | None = None) -> None:
        self._metrics: dict[str, HostMetricsRead] = dict(metrics or {})

    def set_metrics(self, server_key: str, metrics: HostMetricsRead) -> None:
        self._metrics[server_key] = metrics

    async def get_metrics(
        self,
        server_keys: list[str],
        server_capacities: dict[str, tuple[float | None, int | None]] | None = None,
    ) -> dict[str, HostMetricsRead]:
        result: dict[str, HostMetricsRead] = {}
        for key in server_keys:
            if key in self._metrics:
                result[key] = self._metrics[key]
            else:
                result[key] = HostMetricsRead(
                    server_key=key,
                    status=HostStatus.UNKNOWN,
                    freshness=FreshnessStatus.UNKNOWN,
                )
        return result

    async def get_server_metrics(
        self,
        server_key: str,
        memory_gb: float | None = None,
        cpu_cores: int | None = None,
    ) -> HostMetricsRead:
        capacities = {server_key: (memory_gb, cpu_cores)} if memory_gb or cpu_cores else None
        res = await self.get_metrics([server_key], capacities)
        return res[server_key]


class BeszelAdapter:
    """Production edge adapter communicating with Beszel Hub via PocketBase REST API."""

    def __init__(
        self,
        hub_url: str,
        public_url: str = "",
        username: str = "",
        password: str = "",
        token: str = "",
        timeout_seconds: float = 5.0,
        cache_ttl_seconds: float = 15.0,
        freshness_threshold_seconds: float = 120.0,
        key_map: dict[str, str] | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._hub_url = hub_url.rstrip("/")
        self._public_url = public_url.rstrip("/")
        self._username = username
        self._password = password
        self._static_token = bool(token)
        self._token: str | None = token if token else None
        self._timeout_seconds = timeout_seconds
        self._cache_ttl_seconds = cache_ttl_seconds
        self._freshness_threshold_seconds = freshness_threshold_seconds
        self._key_map = {k.lower(): v.lower() for k, v in (key_map or {}).items()}

        self._cached_systems: dict[str, dict[str, Any]] = {}
        self._cache_timestamp: float = 0.0
        self._last_fetch_error: str | None = None
        self._lock = asyncio.Lock()
        self._external_client = http_client

    def _create_client(self) -> httpx.AsyncClient:
        if self._external_client is not None:
            return self._external_client
        return httpx.AsyncClient(timeout=self._timeout_seconds)

    async def _authenticate(self, client: httpx.AsyncClient) -> str:
        if self._static_token and self._token:
            return self._token

        if not self._username or not self._password:
            return ""

        body = {"identity": self._username, "password": self._password}

        # Try PocketBase >=0.23 superuser endpoint
        superuser_url = f"{self._hub_url}/api/collections/_superusers/auth-with-password"
        with contextlib.suppress(httpx.HTTPError):
            resp = await client.post(superuser_url, json=body)
            if resp.status_code == 200:
                token = str(resp.json().get("token", ""))
                self._token = token
                return token


        # Fallback to users endpoint
        users_url = f"{self._hub_url}/api/collections/users/auth-with-password"
        resp = await client.post(users_url, json=body)
        resp.raise_for_status()
        token = str(resp.json().get("token", ""))
        self._token = token
        return token

    async def _fetch_records(self) -> dict[str, dict[str, Any]]:
        client = self._create_client()
        should_close = self._external_client is None
        try:
            token = self._token
            if not token and (self._username or self._static_token):
                token = await self._authenticate(client)

            headers = {}
            if token:
                headers["Authorization"] = f"Bearer {token}"

            url = f"{self._hub_url}/api/collections/systems/records?perPage=100"
            resp = await client.get(url, headers=headers)

            # If token expired, retry auth once
            if resp.status_code == 401 and not self._static_token and self._username:
                self._token = None
                token = await self._authenticate(client)
                headers["Authorization"] = f"Bearer {token}"
                resp = await client.get(url, headers=headers)

            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])

            indexed: dict[str, dict[str, Any]] = {}
            for item in items:
                name = str(item.get("name", "")).strip().lower()
                system_id = str(item.get("id", "")).strip().lower()
                if name:
                    indexed[name] = item
                if system_id:
                    indexed[system_id] = item

            return indexed
        finally:
            if should_close:
                await client.aclose()

    async def _get_fresh_systems(self) -> tuple[dict[str, dict[str, Any]], str | None]:
        now = time.monotonic()
        if self._cached_systems and (now - self._cache_timestamp < self._cache_ttl_seconds):
            return self._cached_systems, None

        async with self._lock:
            # Re-check after acquiring lock
            now = time.monotonic()
            if self._cached_systems and (now - self._cache_timestamp < self._cache_ttl_seconds):
                return self._cached_systems, None

            try:
                records = await self._fetch_records()
                self._cached_systems = records
                self._cache_timestamp = now
                self._last_fetch_error = None
                return records, None
            except Exception as e:
                err = f"Beszel fetch error: {e}"
                logger.warning(err)
                self._last_fetch_error = err
                # If we have stale cache, return it with error noted
                if self._cached_systems:
                    return self._cached_systems, err
                return {}, err

    def _map_item(
        self,
        server_key: str,
        item: dict[str, Any] | None,
        memory_gb: float | None = None,
        cpu_cores: int | None = None,
        fetch_error: str | None = None,
    ) -> HostMetricsRead:
        if item is None:
            freshness = FreshnessStatus.UNREACHABLE if fetch_error else FreshnessStatus.UNKNOWN
            return HostMetricsRead(
                server_key=server_key,
                status=HostStatus.UNKNOWN,
                freshness=freshness,
                error_message=fetch_error,
            )

        raw_status = str(item.get("status", "")).lower()
        if raw_status == "up":
            status = HostStatus.UP
        elif raw_status == "down":
            status = HostStatus.DOWN
        else:
            status = HostStatus.UNKNOWN

        updated_at = None
        raw_updated = item.get("updated")
        if raw_updated:
            with contextlib.suppress(Exception):
                updated_at = _parse_utc_datetime(str(raw_updated))

        # Freshness evaluation
        now_utc = datetime.now(UTC)
        if status == HostStatus.UP:
            if updated_at is not None:
                age_seconds = (now_utc - updated_at).total_seconds()
                if age_seconds <= self._freshness_threshold_seconds:
                    freshness = FreshnessStatus.FRESH
                else:
                    freshness = FreshnessStatus.STALE
            else:
                freshness = FreshnessStatus.STALE
        elif status == HostStatus.DOWN:
            freshness = FreshnessStatus.UNREACHABLE
        else:
            freshness = FreshnessStatus.UNKNOWN

        info = item.get("info")
        if not isinstance(info, dict):
            info = {}

        cpu_percent = float(info["cpu"]) if "cpu" in info and info["cpu"] is not None else None
        memory_percent = float(info["mp"]) if "mp" in info and info["mp"] is not None else None
        disk_percent = float(info["dp"]) if "dp" in info and info["dp"] is not None else None
        uptime_seconds = int(info["u"]) if "u" in info and info["u"] is not None else None

        load_average = None
        raw_la = info.get("la")
        if isinstance(raw_la, list) and len(raw_la) >= 3:
            with contextlib.suppress(ValueError, TypeError):
                load_average = (float(raw_la[0]), float(raw_la[1]), float(raw_la[2]))


        # Memory calculations using server static capacity if available
        memory_total_gb = memory_gb
        memory_used_gb = None
        if memory_total_gb is not None and memory_percent is not None:
            memory_used_gb = round(memory_total_gb * (memory_percent / 100.0), 1)

        # Disk values if available in info
        disk_total_gb = float(info["d"]) if "d" in info and info["d"] is not None else None
        disk_used_gb = float(info["du"]) if "du" in info and info["du"] is not None else None

        upstream_name = item.get("name") or server_key
        upstream_url = None
        if self._public_url:
            upstream_url = f"{self._public_url}/system/{upstream_name}"

        return HostMetricsRead(
            server_key=server_key,
            status=status,
            freshness=freshness,
            cpu_percent=cpu_percent,
            memory_used_gb=memory_used_gb,
            memory_total_gb=memory_total_gb,
            memory_percent=memory_percent,
            disk_used_gb=disk_used_gb,
            disk_total_gb=disk_total_gb,
            disk_percent=disk_percent,
            load_average=load_average,
            uptime_seconds=uptime_seconds,
            upstream_url=upstream_url,
            updated_at=updated_at,
            error_message=fetch_error,
        )

    async def get_metrics(
        self,
        server_keys: list[str],
        server_capacities: dict[str, tuple[float | None, int | None]] | None = None,
    ) -> dict[str, HostMetricsRead]:
        capacities = server_capacities or {}
        systems, error = await self._get_fresh_systems()

        result: dict[str, HostMetricsRead] = {}
        for key in server_keys:
            mapped_name = self._key_map.get(key.lower(), key.lower())
            item = systems.get(mapped_name) or systems.get(key.lower())
            mem_gb, cores = capacities.get(key, (None, None))
            result[key] = self._map_item(
                server_key=key,
                item=item,
                memory_gb=mem_gb,
                cpu_cores=cores,
                fetch_error=error if item is None else None,
            )

        return result

    async def get_server_metrics(
        self,
        server_key: str,
        memory_gb: float | None = None,
        cpu_cores: int | None = None,
    ) -> HostMetricsRead:
        capacities = {server_key: (memory_gb, cpu_cores)} if memory_gb or cpu_cores else None
        res = await self.get_metrics([server_key], capacities)
        return res[server_key]
