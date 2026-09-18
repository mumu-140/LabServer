from fastapi.testclient import TestClient

from .conftest import ALICE_ID, BOB_ID, FakeCoreClient


def test_anonymous_cannot_access_users(anonymous_client: TestClient) -> None:
    assert anonymous_client.get("/users").status_code == 401
    assert (
        anonymous_client.post(
            "/users",
            data={"username": "eve", "display_name": "Eve", "password": "password123"},
        ).status_code
        == 401
    )
    assert (
        anonymous_client.post(
            f"/users/{ALICE_ID}/password", data={"password": "password123"}
        ).status_code
        == 401
    )
    assert (
        anonymous_client.post(
            f"/users/{ALICE_ID}/toggle", data={"enabled": "false"}
        ).status_code
        == 401
    )


def test_regular_member_forbidden_from_users(client: TestClient) -> None:
    # client fixture is logged in as ALICE (UserRole.MEMBER)
    assert client.get("/users").status_code == 403
    assert (
        client.post(
            "/users",
            data={"username": "eve", "display_name": "Eve", "password": "password123"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/users/{ALICE_ID}/password", data={"password": "password123"}
        ).status_code
        == 403
    )
    assert (
        client.post(f"/users/{ALICE_ID}/toggle", data={"enabled": "false"}).status_code
        == 403
    )


def test_navigation_shows_users_link_only_for_admin(
    client: TestClient, admin_client: TestClient
) -> None:
    # Member should not see Users link
    resp_member = client.get("/")
    assert resp_member.status_code == 200
    assert 'href="/users"' not in resp_member.text

    # Admin should see Users link
    resp_admin = admin_client.get("/")
    assert resp_admin.status_code == 200
    assert 'href="/users"' in resp_admin.text


def test_admin_can_list_users(admin_client: TestClient, fake_core: FakeCoreClient) -> None:
    resp = admin_client.get("/users")
    assert resp.status_code == 200
    assert "User Management" in resp.text
    assert "@alice" in resp.text
    assert "@bob" in resp.text


def test_admin_can_provision_user(
    admin_client: TestClient, fake_core: FakeCoreClient
) -> None:
    resp = admin_client.post(
        "/users",
        data={
            "username": "carol",
            "display_name": "Carol Danvers",
            "role": "member",
            "password": "supersecretpassword",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "/users?msg=" in resp.headers["location"]

    # Verify user created and password set in fake_core
    user_names = [u.username for u in fake_core.users]
    assert "carol" in user_names

    set_pw_calls = [
        call for call in fake_core.calls if call[0] == "set_user_password"
    ]
    assert len(set_pw_calls) == 1
    assert set_pw_calls[0][1]["password"] == "supersecretpassword"


def test_admin_provision_validation_errors(admin_client: TestClient) -> None:
    # Empty username
    resp_empty = admin_client.post(
        "/users",
        data={
            "username": "",
            "display_name": "Empty",
            "role": "member",
            "password": "validpassword123",
        },
    )
    assert resp_empty.status_code == 422
    assert "Username and display name cannot be empty" in resp_empty.text

    # Short password
    resp_short = admin_client.post(
        "/users",
        data={
            "username": "dave",
            "display_name": "Dave",
            "role": "member",
            "password": "short",
        },
    )
    assert resp_short.status_code == 422
    assert "at least 8 characters" in resp_short.text

    # Invalid role
    resp_bad_role = admin_client.post(
        "/users",
        data={
            "username": "dave",
            "display_name": "Dave",
            "role": "supergod",
            "password": "validpassword123",
        },
    )
    assert resp_bad_role.status_code == 422
    assert "Invalid role" in resp_bad_role.text


def test_admin_can_reset_password(
    admin_client: TestClient, fake_core: FakeCoreClient
) -> None:
    resp = admin_client.post(
        f"/users/{ALICE_ID}/password",
        data={"password": "newalicepassword123"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "/users?msg=" in resp.headers["location"]

    set_pw_calls = [
        call for call in fake_core.calls if call[0] == "set_user_password"
    ]
    assert any(
        call[1]["user_id"] == ALICE_ID and call[1]["password"] == "newalicepassword123"
        for call in set_pw_calls
    )


def test_admin_cannot_reset_password_too_short(admin_client: TestClient) -> None:
    resp = admin_client.post(
        f"/users/{ALICE_ID}/password",
        data={"password": "short"},
    )
    assert resp.status_code == 422
    assert "at least 8 characters" in resp.text


def test_admin_can_toggle_user_status(
    admin_client: TestClient, fake_core: FakeCoreClient
) -> None:
    # Disable alice
    resp = admin_client.post(
        f"/users/{ALICE_ID}/toggle",
        data={"enabled": "false"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    alice = next(u for u in fake_core.users if u.id == ALICE_ID)
    assert alice.enabled is False

    # Re-enable alice
    resp = admin_client.post(
        f"/users/{ALICE_ID}/toggle",
        data={"enabled": "true"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    alice = next(u for u in fake_core.users if u.id == ALICE_ID)
    assert alice.enabled is True


def test_admin_cannot_disable_self(admin_client: TestClient) -> None:
    # admin_client fixture is BOB_ID
    resp = admin_client.post(
        f"/users/{BOB_ID}/toggle",
        data={"enabled": "false"},
    )
    assert resp.status_code == 422
    assert "Cannot disable your own account" in resp.text
