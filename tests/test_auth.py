"""
Phase 3 regression: registration, login, logout.

Covers the rules called out explicitly in the service layer's own
docstrings — email uniqueness, password strength, self-registration
never being able to create an admin, the generic "invalid
credentials" message for both a wrong password AND an unknown email,
and logout actually revoking the token (not just returning 200).
"""

from tests.factories import (
    DEFAULT_PASSWORD,
    auth_headers,
    login,
    register,
    register_and_login,
)


def test_register_provider_success(client):
    data = register(client, email="new-provider@example.com", role="provider")
    assert data["role"] == "provider"
    assert data["status"] == "active"
    assert "password" not in data
    assert "password_hash" not in data


def test_register_recipient_success(client):
    data = register(client, email="new-recipient@example.com", role="recipient")
    assert data["role"] == "recipient"


def test_register_rejects_admin_role(client):
    resp = client.post(
        "/api/auth/register",
        json={
            "name": "Sneaky",
            "email": "sneaky-admin@example.com",
            "password": DEFAULT_PASSWORD,
            "role": "admin",
        },
    )
    assert resp.status_code == 422
    body = resp.get_json()
    assert body["success"] is False
    assert body["error"] == "VALIDATION_ERROR"


def test_register_rejects_duplicate_email(client):
    register(client, email="dupe@example.com", role="provider")
    resp = client.post(
        "/api/auth/register",
        json={
            "name": "Second One",
            "email": "dupe@example.com",
            "password": DEFAULT_PASSWORD,
            "role": "recipient",
        },
    )
    assert resp.status_code == 409
    assert resp.get_json()["error"] == "EMAIL_ALREADY_REGISTERED"


def test_register_rejects_short_password(client):
    resp = client.post(
        "/api/auth/register",
        json={
            "name": "Weak Password",
            "email": "weak@example.com",
            "password": "abc123",
            "role": "provider",
        },
    )
    assert resp.status_code == 422
    assert resp.get_json()["error"] == "VALIDATION_ERROR"


def test_register_rejects_password_without_letters_or_numbers(client):
    resp = client.post(
        "/api/auth/register",
        json={
            "name": "All Digits",
            "email": "digits@example.com",
            "password": "12345678",
            "role": "provider",
        },
    )
    assert resp.status_code == 422


def test_register_rejects_missing_fields(client):
    resp = client.post("/api/auth/register", json={})
    assert resp.status_code == 422
    assert resp.get_json()["error"] == "VALIDATION_ERROR"


def test_login_success_returns_token_and_user(client):
    register(client, email="login-me@example.com", role="provider")
    token, user = login(client, email="login-me@example.com")
    assert isinstance(token, str) and token
    assert user["email"] == "login-me@example.com"
    assert "password_hash" not in user


def test_login_wrong_password_is_generic_invalid_credentials(client):
    register(client, email="wrongpw@example.com", role="provider")
    resp = client.post(
        "/api/auth/login",
        json={"email": "wrongpw@example.com", "password": "NotMyPassword1"},
    )
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "INVALID_CREDENTIALS"


def test_login_unknown_email_is_same_generic_error(client):
    """
    Deliberately checking this returns the EXACT same error as a
    wrong password (see auth_service.authenticate_user's docstring) —
    a different message/code here would let an attacker enumerate
    which emails are registered.
    """
    resp = client.post(
        "/api/auth/login",
        json={"email": "nobody-here@example.com", "password": "WhoKnows123"},
    )
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "INVALID_CREDENTIALS"
    assert resp.get_json()["message"] == "Invalid email or password."


def test_login_missing_fields_is_validation_error(client):
    resp = client.post("/api/auth/login", json={"email": "only-email@example.com"})
    assert resp.status_code == 422
    assert resp.get_json()["error"] == "VALIDATION_ERROR"


def test_protected_route_requires_bearer_token(client):
    resp = client.get("/api/profile")
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "AUTH_HEADER_MISSING"


def test_protected_route_rejects_garbage_token(client):
    resp = client.get(
        "/api/profile", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "TOKEN_INVALID"


def test_logout_revokes_the_token(client):
    """
    After logout, the SAME token must be rejected on a subsequent
    call — this is what actually proves the blocklist is being
    checked, not just that /logout returns 200.
    """
    token, _ = register_and_login(client, email="logout-me@example.com", role="provider")

    logout_resp = client.post("/api/auth/logout", headers=auth_headers(token))
    assert logout_resp.status_code == 200

    reuse_resp = client.get("/api/profile", headers=auth_headers(token))
    assert reuse_resp.status_code == 401
    assert reuse_resp.get_json()["error"] == "TOKEN_REVOKED"


def test_get_profile_returns_current_user(client):
    token, user = register_and_login(client, email="myprofile@example.com", role="recipient")
    resp = client.get("/api/profile", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.get_json()["data"]["email"] == "myprofile@example.com"
