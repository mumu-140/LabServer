import pytest
from fastapi.testclient import TestClient
from labserver_contracts.auth import SessionRead
from labserver_contracts.common import UserRole
from labserver_web.clients.core import CoreClientError, CoreUnavailableError

from .conftest import ALICE_ID, FakeCoreClient, _make_app


class AuthFakeCoreClient(FakeCoreClient):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.auth_sessions: dict[str, SessionRead] = {}

    def login(self, username: str, password: str) -> tuple[SessionRead, str]:
        self.calls.append(("login", {"username": username, "password": password}))
        self._maybe_fail()
        if username == "alice" and password == "secret":
            session = SessionRead(user_id=ALICE_ID, role=UserRole.MEMBER)
            token = "alice-session-token-xyz"
            self.auth_sessions[token] = session
            return session, token
        raise CoreClientError(401, "unauthorized", "Invalid username or password")

    def logout(self, *, cookies: dict[str, str] | None = None) -> None:
        self.calls.append(("logout", cookies))
        self._maybe_fail()
        token = (cookies or {}).get("labserver_session")
        if token:
            self.auth_sessions.pop(token, None)

    def me(self, *, cookies: dict[str, str] | None = None) -> SessionRead:
        self.calls.append(("me", cookies))
        self._maybe_fail()
        token = (cookies or {}).get("labserver_session")
        if token and token in self.auth_sessions:
            return self.auth_sessions[token]
        raise CoreClientError(401, "unauthorized", "Authentication required")


@pytest.fixture
def auth_core() -> AuthFakeCoreClient:
    return AuthFakeCoreClient()


@pytest.fixture
def web_client(auth_core: AuthFakeCoreClient) -> TestClient:
    app = _make_app(auth_core)
    return TestClient(app)


def test_login_page_renders_anonymously(web_client: TestClient):
    res = web_client.get("/login")
    assert res.status_code == 200
    assert "<form" in res.text
    assert 'name="username"' in res.text
    assert 'name="password"' in res.text


def test_login_success_redirects_and_sets_cookie(
    web_client: TestClient, auth_core: AuthFakeCoreClient
):
    res = web_client.post(
        "/login",
        data={"username": "alice", "password": "secret"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert res.headers["location"] == "/schedule"
    assert "labserver_session" in res.cookies
    assert res.cookies["labserver_session"] == "alice-session-token-xyz"


def test_login_failure_shows_normalized_error(web_client: TestClient):
    res = web_client.post(
        "/login",
        data={"username": "alice", "password": "wrongpassword"},
    )
    assert res.status_code == 401
    assert "Invalid username or password" in res.text
    assert "alice" in res.text


def test_core_unavailable_on_login_is_normalized(
    web_client: TestClient, auth_core: AuthFakeCoreClient
):
    auth_core.error = CoreUnavailableError()
    res = web_client.post(
        "/login",
        data={"username": "alice", "password": "secret"},
    )
    assert res.status_code == 503
    assert "Core service is unavailable" in res.text


def test_viewer_resolves_through_core_cookie(
    web_client: TestClient, auth_core: AuthFakeCoreClient
):
    web_client.post(
        "/login",
        data={"username": "alice", "password": "secret"},
    )
    res = web_client.get("/schedule")
    assert res.status_code == 200


def test_logout_clears_cookie_and_redirects(web_client: TestClient):
    web_client.post(
        "/login",
        data={"username": "alice", "password": "secret"},
    )
    assert "labserver_session" in web_client.cookies

    res = web_client.post("/logout", follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/login"

    assert web_client.get("/schedule").status_code == 401


def test_unauthenticated_request_renders_login_template_with_401(web_client: TestClient):
    res = web_client.get("/schedule")
    assert res.status_code == 401
    assert "Log in to LabServer" in res.text
    assert "<form" in res.text
    assert 'class="main-nav"' not in res.text


def test_unauthenticated_json_request_returns_json_401(web_client: TestClient):
    res = web_client.get("/schedule", headers={"accept": "application/json"})
    assert res.status_code == 401
    assert res.json() == {"detail": "Authentication required"}

