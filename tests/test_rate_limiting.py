"""
Phase 11 regression: in-memory rate limiting on the two endpoints
reachable without a token (app/middleware/rate_limit.py).

These numbers (10 / 300s for login, 5 / 300s for register) are the
real configured limits in app/routes/auth.py — deliberately NOT
mocked to something smaller, so a change to the actual production
config is exactly what would make this test start failing.
"""

import pytest

pytestmark = pytest.mark.slow


def test_login_rate_limit_allows_ten_then_blocks_the_eleventh(client):
    bad_login = {"email": "nobody@example.com", "password": "wrong-password"}

    for attempt in range(10):
        resp = client.post("/api/auth/login", json=bad_login)
        assert resp.status_code == 401, f"attempt {attempt + 1} should be a normal 401"
        assert resp.get_json()["error"] == "INVALID_CREDENTIALS"

    eleventh = client.post("/api/auth/login", json=bad_login)
    assert eleventh.status_code == 429
    body = eleventh.get_json()
    assert body["error"] == "RATE_LIMITED"
    assert "Retry-After" in eleventh.headers


def test_register_rate_limit_allows_five_then_blocks_the_sixth(client):
    def attempt(n):
        return client.post(
            "/api/auth/register",
            json={
                "name": "Rate Test",
                "email": f"rate-test-{n}@example.com",
                "password": "SecurePass123",
                "role": "recipient",
            },
        )

    for n in range(5):
        resp = attempt(n)
        assert resp.status_code == 201, f"attempt {n + 1} should succeed"

    sixth = attempt(5)
    assert sixth.status_code == 429
    assert sixth.get_json()["error"] == "RATE_LIMITED"


def test_rate_limit_is_keyed_per_bucket_not_shared(client):
    """
    Exhausting the LOGIN limit must not affect the REGISTER limit for
    the same caller — they're independent buckets (see
    app/middleware/rate_limit.py's `bucket` parameter).
    """
    bad_login = {"email": "nobody@example.com", "password": "wrong-password"}
    for _ in range(10):
        client.post("/api/auth/login", json=bad_login)
    assert client.post("/api/auth/login", json=bad_login).status_code == 429

    # Registration should still work normally.
    resp = client.post(
        "/api/auth/register",
        json={
            "name": "Still Works",
            "email": "still-works@example.com",
            "password": "SecurePass123",
            "role": "provider",
        },
    )
    assert resp.status_code == 201


def test_rate_limit_is_keyed_per_caller_ip(client):
    """
    A caller hammering /login from one IP should not affect a
    DIFFERENT caller's ability to log in — the limiter is keyed on
    `_client_key()`, which honors X-Forwarded-For.
    """
    bad_login = {"email": "nobody@example.com", "password": "wrong-password"}
    for _ in range(10):
        client.post(
            "/api/auth/login",
            json=bad_login,
            headers={"X-Forwarded-For": "10.0.0.1"},
        )
    blocked = client.post(
        "/api/auth/login", json=bad_login, headers={"X-Forwarded-For": "10.0.0.1"}
    )
    assert blocked.status_code == 429

    other_caller = client.post(
        "/api/auth/login", json=bad_login, headers={"X-Forwarded-For": "10.0.0.2"}
    )
    assert other_caller.status_code == 401  # not rate-limited — different IP
