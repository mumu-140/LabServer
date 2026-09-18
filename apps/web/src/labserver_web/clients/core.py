"""The only Web-to-Core integration point: HTTP calls using canonical DTOs."""

from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID

import httpx
from labserver_contracts.auth import SessionRead
from labserver_contracts.plans import PlanConflictRead, PlanCreate, PlanRead, PlanUpdate
from labserver_contracts.servers import ServerRead
from labserver_contracts.users import UserRead


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

    def list_servers(self) -> list[ServerRead]:
        payload = self._request("GET", "/api/v1/servers").json()
        return [ServerRead.model_validate(item) for item in payload]

    def list_users(self) -> list[UserRead]:
        payload = self._request("GET", "/api/v1/users").json()
        return [UserRead.model_validate(item) for item in payload]

    def list_plans(
        self,
        *,
        server_id: UUID | None = None,
        owner_id: UUID | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        include_cancelled: bool = False,
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
        payload = self._request("GET", "/api/v1/plans", params=params).json()
        return [PlanRead.model_validate(item) for item in payload]

    def get_plan(self, plan_id: UUID) -> PlanRead:
        payload = self._request("GET", f"/api/v1/plans/{plan_id}").json()
        return PlanRead.model_validate(payload)

    def create_plan(self, data: PlanCreate) -> PlanRead:
        payload = self._request("POST", "/api/v1/plans", json=data.model_dump(mode="json")).json()
        return PlanRead.model_validate(payload)

    def update_plan(self, plan_id: UUID, data: PlanUpdate) -> PlanRead:
        body = data.model_dump(mode="json", exclude_unset=True)
        payload = self._request("PATCH", f"/api/v1/plans/{plan_id}", json=body).json()
        return PlanRead.model_validate(payload)

    def cancel_plan(self, plan_id: UUID) -> PlanRead:
        payload = self._request("POST", f"/api/v1/plans/{plan_id}/cancel").json()
        return PlanRead.model_validate(payload)

    def list_conflicts(self, plan_id: UUID) -> list[PlanConflictRead]:
        payload = self._request("GET", f"/api/v1/plans/{plan_id}/conflicts").json()
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
