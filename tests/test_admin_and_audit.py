"""
Phase 11 regression: admin user management + audit log access.

This is the automated version of the manual Postman walkthrough in
README.md section 15e — every behavior verified by hand there has a
matching test here so it can never silently regress again.
"""

from tests.factories import (
    auth_headers,
    create_provider,
    create_recipient,
    make_admin_token,
    register_and_login,
)


# --------------------------------------------------------- list/filter users


def test_admin_can_list_all_users(client, app):
    admin_token, _ = make_admin_token(client, app)
    create_provider(client, email="p1@example.com")
    create_recipient(client, app, email="r1@example.com")

    resp = client.get("/api/admin/users", headers=auth_headers(admin_token))
    assert resp.status_code == 200
    emails = {u["email"] for u in resp.get_json()["data"]["users"]}
    assert {"p1@example.com", "r1@example.com"}.issubset(emails)


def test_admin_can_filter_by_role_and_status(client, app):
    admin_token, _ = make_admin_token(client, app)
    create_provider(client, email="filter-provider@example.com")
    create_recipient(client, app, email="filter-recipient@example.com")

    resp = client.get(
        "/api/admin/users?role=recipient&status=active",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200
    users = resp.get_json()["data"]["users"]
    assert all(u["role"] == "recipient" and u["status"] == "active" for u in users)
    assert any(u["email"] == "filter-recipient@example.com" for u in users)


def test_admin_search_matches_name_or_email_case_insensitively(client, app):
    admin_token, _ = make_admin_token(client, app)
    create_provider(client, email="green@example.com", org_name="Green Table Restaurant")

    resp = client.get("/api/admin/users?search=GREEN", headers=auth_headers(admin_token))
    assert resp.status_code == 200
    emails = {u["email"] for u in resp.get_json()["data"]["users"]}
    assert "green@example.com" in emails


def test_admin_invalid_role_filter_is_validation_error(client, app):
    admin_token, _ = make_admin_token(client, app)
    resp = client.get(
        "/api/admin/users?role=not-a-real-role", headers=auth_headers(admin_token)
    )
    assert resp.status_code == 422
    assert resp.get_json()["error"] == "VALIDATION_ERROR"


def test_non_admin_cannot_list_users(client):
    token, _ = register_and_login(client, email="rando@example.com", role="provider")
    resp = client.get("/api/admin/users", headers=auth_headers(token))
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "FORBIDDEN"


# --------------------------------------------------- deactivate / reactivate


def test_deactivate_and_reactivate_round_trip(client, app):
    admin_token, admin_id = make_admin_token(client, app)
    target = create_provider(client, email="target@example.com")
    target_user_id = target["user"]["id"]

    deactivate_resp = client.post(
        f"/api/admin/users/{target_user_id}/deactivate", headers=auth_headers(admin_token)
    )
    assert deactivate_resp.status_code == 200
    assert deactivate_resp.get_json()["data"]["status"] == "inactive"

    activate_resp = client.post(
        f"/api/admin/users/{target_user_id}/activate", headers=auth_headers(admin_token)
    )
    assert activate_resp.status_code == 200
    assert activate_resp.get_json()["data"]["status"] == "active"


def test_deactivation_blocks_existing_token_immediately(client, app):
    """
    The core Phase 11 security guarantee: deactivating a user takes
    effect on their NEXT request, even with a token that hasn't
    expired — because token_required re-checks AccountStatus every
    time, not just at login.
    """
    admin_token, _ = make_admin_token(client, app)
    target = create_provider(client, email="soon-deactivated@example.com")

    # Confirm the token is good before deactivation.
    assert client.get(
        "/api/providers/profile", headers=auth_headers(target["token"])
    ).status_code == 200

    client.post(
        f"/api/admin/users/{target['user']['id']}/deactivate",
        headers=auth_headers(admin_token),
    )

    blocked = client.get(
        "/api/providers/profile", headers=auth_headers(target["token"])
    )
    assert blocked.status_code == 401
    assert blocked.get_json()["error"] == "ACCOUNT_INACTIVE"


def test_deactivated_user_cannot_log_in_again(client, app):
    admin_token, _ = make_admin_token(client, app)
    target = create_provider(client, email="cant-login@example.com")
    client.post(
        f"/api/admin/users/{target['user']['id']}/deactivate",
        headers=auth_headers(admin_token),
    )

    resp = client.post(
        "/api/auth/login",
        json={"email": "cant-login@example.com", "password": "SecurePass123"},
    )
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "ACCOUNT_INACTIVE"


def test_deactivate_is_idempotent(client, app):
    admin_token, _ = make_admin_token(client, app)
    target = create_provider(client, email="deactivate-twice@example.com")
    user_id = target["user"]["id"]

    first = client.post(f"/api/admin/users/{user_id}/deactivate", headers=auth_headers(admin_token))
    second = client.post(f"/api/admin/users/{user_id}/deactivate", headers=auth_headers(admin_token))
    assert first.status_code == 200
    assert second.status_code == 200  # not an error the second time


def test_admin_cannot_deactivate_own_account(client, app):
    admin_token, admin_id = make_admin_token(client, app)
    resp = client.post(
        f"/api/admin/users/{admin_id}/deactivate", headers=auth_headers(admin_token)
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "CANNOT_DEACTIVATE_SELF"


def test_non_admin_cannot_deactivate_anyone(client, app):
    provider = create_provider(client, email="cant-deactivate@example.com")
    victim = create_provider(client, email="victim@example.com", org_name="Victim Org")

    resp = client.post(
        f"/api/admin/users/{victim['user']['id']}/deactivate",
        headers=auth_headers(provider["token"]),
    )
    assert resp.status_code == 403


# ------------------------------------------------------------------- audit


def test_registration_and_login_are_audited(client, app):
    admin_token, _ = make_admin_token(client, app)
    register_and_login(client, email="audited-user@example.com", role="provider")

    resp = client.get(
        "/api/audit-logs?action=user_registered", headers=auth_headers(admin_token)
    )
    descriptions = [e["description"] for e in resp.get_json()["data"]["audit_logs"]]
    assert any("provider" in d for d in descriptions)

    login_resp = client.get(
        "/api/audit-logs?action=login", headers=auth_headers(admin_token)
    )
    assert login_resp.get_json()["data"]["pagination"]["total"] >= 1


def test_failed_login_is_audited_without_leaking_account_existence(client, app):
    admin_token, _ = make_admin_token(client, app)
    client.post(
        "/api/auth/login",
        json={"email": "totally-made-up@example.com", "password": "WhoKnows123"},
    )

    resp = client.get(
        "/api/audit-logs?action=login_failed", headers=auth_headers(admin_token)
    )
    entries = resp.get_json()["data"]["audit_logs"]
    assert any("totally-made-up@example.com" in (e["description"] or "") for e in entries)
    # No known user -> user_id must be null on that entry.
    matching = [e for e in entries if "totally-made-up@example.com" in (e["description"] or "")]
    assert matching[0]["user_id"] is None


def test_account_deactivation_is_audited_with_admin_as_actor(client, app):
    admin_token, admin_id = make_admin_token(client, app)
    target = create_provider(client, email="audit-deactivate@example.com")
    client.post(
        f"/api/admin/users/{target['user']['id']}/deactivate",
        headers=auth_headers(admin_token),
    )

    resp = client.get(
        "/api/audit-logs?action=account_deactivated", headers=auth_headers(admin_token)
    )
    entries = resp.get_json()["data"]["audit_logs"]
    assert len(entries) == 1
    assert entries[0]["user_id"] == admin_id
    assert entries[0]["resource_id"] == target["user"]["id"]


def test_audit_log_filters_by_resource_type(client, app):
    admin_token, _ = make_admin_token(client, app)
    register_and_login(client, email="resource-type-check@example.com", role="provider")

    resp = client.get(
        "/api/audit-logs?resource_type=user", headers=auth_headers(admin_token)
    )
    entries = resp.get_json()["data"]["audit_logs"]
    assert len(entries) >= 1
    assert all(e["resource_type"] == "user" for e in entries)


def test_audit_log_rejects_malformed_date(client, app):
    admin_token, _ = make_admin_token(client, app)
    resp = client.get(
        "/api/audit-logs?start_date=not-a-date", headers=auth_headers(admin_token)
    )
    assert resp.status_code == 422
    assert resp.get_json()["error"] == "VALIDATION_ERROR"


def test_non_admin_cannot_read_audit_logs(client):
    token, _ = register_and_login(client, email="nosy@example.com", role="recipient")
    resp = client.get("/api/audit-logs", headers=auth_headers(token))
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "FORBIDDEN"
