"""
Phase 10 regression: reporting endpoints.

These are deliberately "smoke" tests — they confirm the numbers are
internally consistent and that scoping rules (a provider/recipient
sees only their own data; only an admin sees the platform-wide view)
are enforced, without re-deriving every aggregation by hand.
"""

from app.extensions import db
from app.models import DistributionRecord
from tests.factories import auth_headers, create_listing, create_provider, create_recipient, make_admin_token


def _complete_one_distribution(client, app, quantity=15, suffix=""):
    provider = create_provider(client, email=f"provider{suffix}@example.com")
    listing = create_listing(client, provider["token"], quantity=quantity)
    recipient = create_recipient(client, app, email=f"recipient{suffix}@example.com")

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
    _complete_one_distribution(client, app, quantity=20, suffix="-second")

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


def test_platform_summary_distribution_counts_match_database_records(
    client, app, db_session
):
    admin_token, _ = make_admin_token(client, app)
    provider = create_provider(client)
    listing = create_listing(client, provider["token"])
    recipient = create_recipient(client, app)
    request = client.post(
        "/api/requests",
        json={"listing_id": listing["id"], "requested_quantity": 10},
        headers=auth_headers(recipient["token"]),
    ).get_json()["data"]
    client.post(
        f"/api/requests/{request['id']}/accept",
        headers=auth_headers(provider["token"]),
    )
    pickup = client.post(
        f"/api/requests/{request['id']}/schedule-pickup",
        headers=auth_headers(provider["token"]),
    ).get_json()["data"]

    scheduled_summary = client.get(
        "/api/reports/platform-summary", headers=auth_headers(admin_token)
    ).get_json()["data"]
    assert scheduled_summary["total_distributions"] == 0
    assert scheduled_summary["completed_distributions"] == 0

    completed = client.post(
        f"/api/pickups/{pickup['id']}/complete",
        headers=auth_headers(provider["token"]),
    )
    assert completed.status_code == 200

    completed_summary = client.get(
        "/api/reports/platform-summary", headers=auth_headers(admin_token)
    ).get_json()["data"]
    assert completed_summary["completed_distributions"] == 1
    assert completed_summary["total_distributions"] == 1
    assert completed_summary["available_distributions"] == 0
    assert completed_summary["cancelled_distributions"] == 0

    repeated_summary = client.get(
        "/api/reports/platform-summary", headers=auth_headers(admin_token)
    ).get_json()["data"]
    assert repeated_summary["completed_distributions"] == 1
    assert repeated_summary["total_distributions"] == 1

    for status in ("available", "cancelled"):
        db_session.add(
            DistributionRecord(
                listing_id=listing["id"],
                provider_id=provider["profile"]["id"],
                recipient_id=recipient["profile"]["id"],
                quantity=1,
                completion_status=status,
            )
        )
    db_session.commit()

    database_counts = dict(
        db_session.query(
            DistributionRecord.completion_status,
            db.func.count(DistributionRecord.id),
        )
        .group_by(DistributionRecord.completion_status)
        .all()
    )
    final_summary = client.get(
        "/api/reports/platform-summary", headers=auth_headers(admin_token)
    ).get_json()["data"]

    assert final_summary["available_distributions"] == database_counts.get("available", 0) == 1
    assert final_summary["cancelled_distributions"] == database_counts.get("cancelled", 0) == 1
    assert final_summary["completed_distributions"] == database_counts.get("completed", 0) == 1
    assert final_summary["total_distributions"] == db_session.query(
        DistributionRecord.id
    ).count() == sum(database_counts.values()) == 3


def test_report_rejects_malformed_date(client, app):
    provider = create_provider(client)
    resp = client.get(
        "/api/reports/distributions/summary?start_date=not-a-date",
        headers=auth_headers(provider["token"]),
    )
    assert resp.status_code == 422
    assert resp.get_json()["error"] == "VALIDATION_ERROR"
