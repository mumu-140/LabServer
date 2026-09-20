"""The only Web-to-Core integration point: HTTP calls using canonical DTOs."""

from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID

import httpx
from labserver_contracts.auth import SessionRead
from labserver_contracts.monitoring import DashboardRead, HostMetricsRead
from labserver_contracts.plans import PlanConflictRead, PlanCreate, PlanRead, PlanUpdate
from labserver_contracts.runtime import RuntimeOverviewRead
from labserver_contracts.servers import ServerRead
from labserver_contracts.users import UserCreate, UserRead, UserUpdate


class CoreClientError(Exception):

    """Core responded with a non-success status; carries the error envelope."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(f"Core returned {status_code} ({code}): {message}")
        self.status_code = status_code
        self.code = code
        self.message = message


class CoreUnavailableError(CoreClientError):
    """Core could not be reached (transport failure); safe to show users."""

    def __init__(self, message: str = "Core service is unavailable") -> None:
        super().__init__(503, "service_unavailable", message)


class CoreClient:
    def __init__(
        self,
        base_url: str,
        *,
        client_factory: Callable[[str], httpx.Client] | None = None,
    ) -> None:
        factory = client_factory or (lambda url: httpx.Client(base_url=url, timeout=10.0))
        self._client = factory(base_url)

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.RequestError as error:
            raise CoreUnavailableError() from error
        if response.status_code >= 400:
            try:
                detail = response.json()["error"]
                code, message = str(detail.get("code", "error")), str(
                    detail.get("message", response.text)
                )
            except Exception:
                code, message = "error", response.text
            raise CoreClientError(response.status_code, code, message)
        return response

    def list_servers(self, *, cookies: dict[str, str] | None = None) -> list[ServerRead]:
        payload = self._request("GET", "/api/v1/servers", cookies=cookies).json()
        return [ServerRead.model_validate(item) for item in payload]

    def list_users(self, *, cookies: dict[str, str] | None = None) -> list[UserRead]:
        payload = self._request("GET", "/api/v1/users", cookies=cookies).json()
        return [UserRead.model_validate(item) for item in payload]

    def create_user(
        self, data: UserCreate, *, cookies: dict[str, str] | None = None
    ) -> UserRead:
        payload = self._request(
            "POST", "/api/v1/users", json=data.model_dump(mode="json"), cookies=cookies
        ).json()
        return UserRead.model_validate(payload)

    def set_user_password(
        self, user_id: UUID, password: str, *, cookies: dict[str, str] | None = None
    ) -> None:
        self._request(
            "POST",
            f"/api/v1/users/{user_id}/password",
            json={"password": password},
            cookies=cookies,
        )

    def update_user(
        self, user_id: UUID, data: UserUpdate, *, cookies: dict[str, str] | None = None
    ) -> UserRead:
        payload = self._request(
            "PATCH",
            f"/api/v1/users/{user_id}",
            json=data.model_dump(mode="json", exclude_unset=True),
            cookies=cookies,
        ).json()
        return UserRead.model_validate(payload)

    def list_plans(
        self,
        *,
        server_id: UUID | None = None,
        owner_id: UUID | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        include_cancelled: bool = False,
        cookies: dict[str, str] | None = None,
    ) -> list[PlanRead]:
        params: dict[str, Any] = {"include_cancelled": str(include_cancelled).lower()}
        if server_id is not None:
            params["server_id"] = str(server_id)
        if owner_id is not None:
            params["owner_id"] = str(owner_id)
        if start is not None:
            params["start"] = start.isoformat()
        if end is not None:
            params["end"] = end.isoformat()
        payload = self._request("GET", "/api/v1/plans", params=params, cookies=cookies).json()
        return [PlanRead.model_validate(item) for item in payload]

    def get_plan(self, plan_id: UUID, *, cookies: dict[str, str] | None = None) -> PlanRead:
        payload = self._request("GET", f"/api/v1/plans/{plan_id}", cookies=cookies).json()
        return PlanRead.model_validate(payload)

    def create_plan(
        self, data: PlanCreate, *, cookies: dict[str, str] | None = None
    ) -> PlanRead:
        payload = self._request(
            "POST", "/api/v1/plans", json=data.model_dump(mode="json"), cookies=cookies
        ).json()
        return PlanRead.model_validate(payload)

    def update_plan(
        self, plan_id: UUID, data: PlanUpdate, *, cookies: dict[str, str] | None = None
    ) -> PlanRead:
        body = data.model_dump(mode="json", exclude_unset=True)
        payload = self._request(
            "PATCH", f"/api/v1/plans/{plan_id}", json=body, cookies=cookies
        ).json()
        return PlanRead.model_validate(payload)

    def cancel_plan(self, plan_id: UUID, *, cookies: dict[str, str] | None = None) -> PlanRead:
        payload = self._request(
            "POST", f"/api/v1/plans/{plan_id}/cancel", cookies=cookies
        ).json()
        return PlanRead.model_validate(payload)

    def list_conflicts(
        self, plan_id: UUID, *, cookies: dict[str, str] | None = None
    ) -> list[PlanConflictRead]:
        payload = self._request(
            "GET", f"/api/v1/plans/{plan_id}/conflicts", cookies=cookies
        ).json()
        return [PlanConflictRead.model_validate(item) for item in payload]

    def login(self, username: str, password: str) -> tuple[SessionRead, str]:
        response = self._request(
            "POST",
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        session = SessionRead.model_validate(response.json())
        token = response.cookies.get("labserver_session") or ""
        return session, token

    def logout(self, *, cookies: dict[str, str] | None = None) -> None:
        self._request("POST", "/api/v1/auth/logout", cookies=cookies)

    def me(self, *, cookies: dict[str, str] | None = None) -> SessionRead:
        response = self._request("GET", "/api/v1/auth/me", cookies=cookies)
        return SessionRead.model_validate(response.json())

    def get_dashboard(self, *, cookies: dict[str, str] | None = None) -> DashboardRead:
        response = self._request("GET", "/api/v1/monitoring/dashboard", cookies=cookies)
        return DashboardRead.model_validate(response.json())

    def get_server_metrics(
        self, server_key: str, *, cookies: dict[str, str] | None = None
    ) -> HostMetricsRead:
        response = self._request(
            "GET", f"/api/v1/monitoring/servers/{server_key}", cookies=cookies
        )
        return HostMetricsRead.model_validate(response.json())

    def get_runtime_overview(
        self, *, cookies: dict[str, str] | None = None
    ) -> RuntimeOverviewRead:
        response = self._request("GET", "/api/v1/runtime/overview", cookies=cookies)
        return RuntimeOverviewRead.model_validate(response.json())


