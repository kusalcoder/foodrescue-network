"""
Phase 4/5 regression: provider and recipient profile management, plus
the Phase 6 admin-verification endpoint that lives in
app/routes/recipients.py.
"""

from tests.factories import (
    auth_headers,
    create_provider,
    create_recipient,
    make_admin_token,
    register_and_login,
)


# ---------------------------------------------------------------- provider


def test_provider_can_create_and_fetch_own_profile(client):
    fx = create_provider(client)
    resp = client.get("/api/providers/profile", headers=auth_headers(fx["token"]))
    assert resp.status_code == 200
    assert resp.get_json()["data"]["organization_name"] == "Green Table Restaurant"


def test_provider_cannot_create_two_profiles(client):
    fx = create_provider(client)
    resp = client.post(
        "/api/providers/profile",
        json={"organization_name": "Second Attempt"},
        headers=auth_headers(fx["token"]),
    )
    assert resp.status_code == 409


def test_provider_can_update_profile(client):
    fx = create_provider(client)
    resp = client.put(
        "/api/providers/profile",
        json={"description": "Updated description."},
        headers=auth_headers(fx["token"]),
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["description"] == "Updated description."
    # unrelated fields are untouched by a partial update
    assert resp.get_json()["data"]["organization_name"] == "Green Table Restaurant"


def test_recipient_cannot_create_provider_profile(client):
    token, _ = register_and_login(client, email="rcpt-not-provider@example.com", role="recipient")
    resp = client.post(
        "/api/providers/profile",
        json={"organization_name": "Should Not Work"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "FORBIDDEN"


def test_provider_profile_get_before_creation_is_404(client):
    token, _ = register_and_login(client, email="no-profile-yet@example.com", role="provider")
    resp = client.get("/api/providers/profile", headers=auth_headers(token))
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "PROFILE_NOT_FOUND"


# --------------------------------------------------------------- recipient


def test_recipient_profile_starts_pending_verification(client):
    fx = create_recipient(client, client.application, verified=False)
    assert fx["profile"]["verification_status"] == "pending"


def test_provider_cannot_create_recipient_profile(client):
    fx = create_provider(client, email="prov-not-rcpt@example.com")
    resp = client.post(
        "/api/recipients/profile",
        json={"organization_name": "Should Not Work"},
        headers=auth_headers(fx["token"]),
    )
    assert resp.status_code == 403


def test_admin_can_verify_a_recipient(client, app):
    admin_token, _ = make_admin_token(client, app)
    fx = create_recipient(client, app, email="to-verify@example.com", verified=False)
    assert fx["profile"]["verification_status"] == "pending"

    resp = client.post(
        f"/api/recipients/{fx['profile']['id']}/verify",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["verification_status"] == "verified"


def test_non_admin_cannot_verify_a_recipient(client, app):
    fx = create_recipient(client, app, email="cant-self-verify@example.com", verified=False)
    resp = client.post(
        f"/api/recipients/{fx['profile']['id']}/verify",
        headers=auth_headers(fx["token"]),
    )
    assert resp.status_code == 403
