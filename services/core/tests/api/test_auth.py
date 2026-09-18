from uuid import uuid4

from labserver_contracts.common import UserRole
from labserver_core.application.passwords import Argon2PasswordHasher
from labserver_core.persistence.repositories import UserRepository

from .conftest import ADMIN_ID, MEMBER_ID, ApiContext


def _set_user_password(api_context: ApiContext, user_id, raw_password: str) -> None:
    hasher = Argon2PasswordHasher()
    hashed = hasher.hash(raw_password)
    with api_context.session_factory() as session:
        UserRepository(session).set_password_hash(user_id, hashed)
        session.commit()


def test_me_without_cookie_is_unauthorized(api_context: ApiContext):
    response = api_context.client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "unauthorized",
            "message": "Authentication required",
        }
    }


def test_login_success_and_me_and_logout(api_context: ApiContext):
    _set_user_password(api_context, MEMBER_ID, "member-secret-password")

    # 1. Login
    login_res = api_context.client.post(
        "/api/v1/auth/login",
        json={"username": "member", "password": "member-secret-password"},
    )
    assert login_res.status_code == 200
    data = login_res.json()
    assert data["user_id"] == str(MEMBER_ID)
    assert data["role"] == "member"
    assert "labserver_session" in login_res.cookies

    # 2. GET /auth/me using the session cookie
    me_res = api_context.client.get("/api/v1/auth/me")
    assert me_res.status_code == 200
    assert me_res.json() == {"user_id": str(MEMBER_ID), "role": "member"}

    # 3. Logout
    logout_res = api_context.client.post("/api/v1/auth/logout")
    assert logout_res.status_code == 204

    # 4. Subsequent me fails
    me_after = api_context.client.get("/api/v1/auth/me")
    assert me_after.status_code == 401


def test_login_uniform_failure(api_context: ApiContext):
    _set_user_password(api_context, MEMBER_ID, "member-secret-password")

    # Unknown user
    res1 = api_context.client.post(
        "/api/v1/auth/login",
        json={"username": "nonexistent", "password": "member-secret-password"},
    )
    assert res1.status_code == 401
    assert res1.json() == {
        "error": {"code": "unauthorized", "message": "Invalid username or password"}
    }

    # Wrong password
    res2 = api_context.client.post(
        "/api/v1/auth/login",
        json={"username": "member", "password": "wrong-password"},
    )
    assert res2.status_code == 401
    assert res2.json() == res1.json()


def test_admin_set_password_and_login(api_context: ApiContext):
    _set_user_password(api_context, ADMIN_ID, "admin-master-password")

    # Login as admin
    login_res = api_context.client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin-master-password"},
    )
    assert login_res.status_code == 200

    # Set password for member
    set_res = api_context.client.post(
        f"/api/v1/users/{MEMBER_ID}/password",
        json={"password": "brand-new-member-pass-8chars"},
    )
    assert set_res.status_code == 204

    # Member can now login with new password
    # Clear admin cookie first
    api_context.client.cookies.clear()
    member_login = api_context.client.post(
        "/api/v1/auth/login",
        json={"username": "member", "password": "brand-new-member-pass-8chars"},
    )
    assert member_login.status_code == 200
    assert member_login.json()["user_id"] == str(MEMBER_ID)


def test_member_cannot_set_password(api_context: ApiContext):
    _set_user_password(api_context, MEMBER_ID, "member-secret-password")

    login_res = api_context.client.post(
        "/api/v1/auth/login",
        json={"username": "member", "password": "member-secret-password"},
    )
    assert login_res.status_code == 200

    set_res = api_context.client.post(
        f"/api/v1/users/{MEMBER_ID}/password",
        json={"password": "brand-new-member-pass-8chars"},
    )
    assert set_res.status_code == 403
    assert set_res.json() == {
        "error": {"code": "forbidden", "message": "Administrator privileges are required"}
    }


def test_set_password_not_found(api_context: ApiContext):
    _set_user_password(api_context, ADMIN_ID, "admin-master-password")

    login_res = api_context.client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin-master-password"},
    )
    assert login_res.status_code == 200

    random_id = uuid4()
    set_res = api_context.client.post(
        f"/api/v1/users/{random_id}/password",
        json={"password": "brand-new-member-pass-8chars"},
    )
    assert set_res.status_code == 404
    assert set_res.json() == {
        "error": {"code": "not_found", "message": f"User {random_id} does not exist"}
    }


def test_set_password_validation_error_too_short(api_context: ApiContext):
    api_context.act_as(ADMIN_ID, UserRole.ADMIN)

    set_res = api_context.client.post(
        f"/api/v1/users/{MEMBER_ID}/password",
        json={"password": "short"},  # min_length=8
    )
    assert set_res.status_code == 422
    assert set_res.json()["error"]["code"] == "validation_error"
