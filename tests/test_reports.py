"""
Phase 10 regression: reporting endpoints.

These are deliberately "smoke" tests — they confirm the numbers are
internally consistent and that scoping rules (a provider/recipient
sees only their own data; only an admin sees the platform-wide view)
are enforced, without re-deriving every aggregation by hand.
"""

from tests.factories import auth_headers, create_listing, create_provider, create_recipient, make_admin_token


def _complete_one_distribution(client, app, quantity=15):
    provider = create_provider(client)
    listing = create_listing(client, provider["token"], quantity=quantity)
    recipient = create_recipient(client, app)

    req = client.post(
        "/api/requests",
        json={"listing_id": listing["id"], "requested_quantity": quantity},
        headers=auth_headers(recipient["token"]),
    ).get_json()["data"]
    client.post(f"/api/requests/{req['id']}/accept", headers=auth_headers(provider["token"]))
    pickup = client.post(
        f"/api/requests/{req['id']}/schedule-pickup", headers=auth_headers(provider["token"])
    ).get_json()["data"]
    client.post(f"/api/pickups/{pickup['id']}/complete", headers=auth_headers(provider["token"]))
    return provider, recipient


def test_provider_distribution_summary_reflects_their_own_activity(client, app):
    provider, _ = _complete_one_distribution(client, app, quantity=15)
    resp = client.get(
        "/api/reports/distributions/summary", headers=auth_headers(provider["token"])
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["total_distributions"] == 1
    assert data["total_quantity"] == 15.0


def test_provider_cannot_see_another_providers_numbers_via_query_param(client, app):
    """
    provider_id/recipient_id query params are admin-only overrides —
    a provider passing someone else's id must still only see their
    own data (the route pins it, ignoring the param).
    """
    provider_a, _ = _complete_one_distribution(client, app, quantity=15)
    provider_b = create_provider(client, email="provider-b@example.com", org_name="Org B")

    resp = client.get(
        f"/api/reports/distributions/summary?provider_id={provider_a['profile']['id']}",
        headers=auth_headers(provider_b["token"]),
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["total_distributions"] == 0


def test_admin_sees_platform_wide_totals_by_default(client, app):
    admin_token, _ = make_admin_token(client, app)
    _complete_one_distribution(client, app, quantity=10)
    _complete_one_distribution(client, app, quantity=20)

    resp = client.get(
        "/api/reports/distributions/summary", headers=auth_headers(admin_token)
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["total_distributions"] == 2
    assert data["total_quantity"] == 30.0


def test_distribution_by_category_breakdown(client, app):
    provider, _ = _complete_one_distribution(client, app, quantity=15)
    resp = client.get(
        "/api/reports/distributions/by-category", headers=auth_headers(provider["token"])
    )
    assert resp.status_code == 200
    categories = resp.get_json()["data"]["categories"]
    assert len(categories) == 1
    assert categories[0]["category"] == "prepared_food"
    assert categories[0]["total_quantity"] == 15.0


def test_my_activity_shape_differs_by_role(client, app):
    provider, recipient = _complete_one_distribution(client, app)

    provider_activity = client.get(
        "/api/reports/my-activity", headers=auth_headers(provider["token"])
    ).get_json()["data"]
    assert "listings_by_status" in provider_activity

    recipient_activity = client.get(
        "/api/reports/my-activity", headers=auth_headers(recipient["token"])
    ).get_json()["data"]
    assert "listings_by_status" not in recipient_activity


def test_platform_summary_is_admin_only(client, app):
    admin_token, _ = make_admin_token(client, app)
    provider = create_provider(client)

    ok = client.get("/api/reports/platform-summary", headers=auth_headers(admin_token))
    assert ok.status_code == 200
    data = ok.get_json()["data"]
    assert "users_by_role" in data
    assert "listings_by_status" in data
    assert "recipients_by_verification" in data

    forbidden = client.get(
        "/api/reports/platform-summary", headers=auth_headers(provider["token"])
    )
    assert forbidden.status_code == 403


def test_report_rejects_malformed_date(client, app):
    provider = create_provider(client)
    resp = client.get(
        "/api/reports/distributions/summary?start_date=not-a-date",
        headers=auth_headers(provider["token"]),
    )
    assert resp.status_code == 422
    assert resp.get_json()["error"] == "VALIDATION_ERROR"
