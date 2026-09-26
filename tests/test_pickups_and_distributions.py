"""
Phase 7 regression: pickup scheduling/confirmation/completion, and the
append-only DistributionRecord that completion creates.

This file also contains the single "full lifecycle" integration test
the Phase 12 preview specifically calls for: register -> profile ->
listing -> request -> accept -> schedule -> confirm -> complete ->
distribution record.
"""

from tests.factories import (
    auth_headers,
    create_listing,
    create_provider,
    create_recipient,
)


def _accepted_request(client, app, quantity=50, requested=10):
    provider = create_provider(client)
    listing = create_listing(client, provider["token"], quantity=quantity)
    recipient = create_recipient(client, app)

    req = client.post(
        "/api/requests",
        json={"listing_id": listing["id"], "requested_quantity": requested},
        headers=auth_headers(recipient["token"]),
    ).get_json()["data"]
    client.post(f"/api/requests/{req['id']}/accept", headers=auth_headers(provider["token"]))

    return provider, listing, recipient, req


def test_full_lifecycle_register_to_distribution(client, app):
    """
    The end-to-end happy path: every phase's contribution to the
    platform, exercised in one continuous flow. If this test fails,
    something broke the seam BETWEEN phases, not necessarily any one
    phase's logic in isolation.
    """
    provider, listing, recipient, req = _accepted_request(client, app, quantity=20, requested=20)
    assert req["status"] == "accepted"

    schedule_resp = client.post(
        f"/api/requests/{req['id']}/schedule-pickup",
        json={"confirmation_info": "Ring the back door bell."},
        headers=auth_headers(provider["token"]),
    )
    assert schedule_resp.status_code == 201
    pickup = schedule_resp.get_json()["data"]
    assert pickup["status"] == "scheduled"

    confirm_resp = client.post(
        f"/api/pickups/{pickup['id']}/confirm", headers=auth_headers(recipient["token"])
    )
    assert confirm_resp.status_code == 200
    assert confirm_resp.get_json()["data"]["status"] == "confirmed"

    complete_resp = client.post(
        f"/api/pickups/{pickup['id']}/complete",
        json={"confirmation_info": "Signed by J. Doe"},
        headers=auth_headers(provider["token"]),
    )
    assert complete_resp.status_code == 200
    assert complete_resp.get_json()["data"]["status"] == "completed"

    # The request should now be COMPLETED too.
    req_after = client.get(
        f"/api/requests/{req['id']}", headers=auth_headers(recipient["token"])
    ).get_json()["data"]
    assert req_after["status"] == "completed"

    # Fully-claimed listing should have flipped to COLLECTED.
    listing_after = client.get(
        f"/api/listings/{listing['id']}", headers=auth_headers(provider["token"])
    ).get_json()["data"]
    assert listing_after["status"] == "collected"

    # A DistributionRecord must now exist and be visible to both sides.
    provider_dist = client.get(
        "/api/distributions", headers=auth_headers(provider["token"])
    ).get_json()["data"]["distributions"]
    recipient_dist = client.get(
        "/api/distributions", headers=auth_headers(recipient["token"])
    ).get_json()["data"]["distributions"]

    assert len(provider_dist) == 1
    assert len(recipient_dist) == 1
    assert provider_dist[0]["id"] == recipient_dist[0]["id"]
    assert provider_dist[0]["quantity"] == 20.0
    assert provider_dist[0]["completion_status"] == "completed"


def test_only_accepted_request_can_have_pickup_scheduled(client, app):
    provider = create_provider(client)
    listing = create_listing(client, provider["token"])
    recipient = create_recipient(client, app)
    req = client.post(
        "/api/requests",
        json={"listing_id": listing["id"], "requested_quantity": 5},
        headers=auth_headers(recipient["token"]),
    ).get_json()["data"]  # still PENDING, never accepted

    resp = client.post(
        f"/api/requests/{req['id']}/schedule-pickup",
        headers=auth_headers(provider["token"]),
    )
    assert resp.status_code == 409
    assert resp.get_json()["error"] == "INVALID_REQUEST_STATE"


def test_cannot_double_schedule_pickup_for_same_request(client, app):
    provider, listing, recipient, req = _accepted_request(client, app)
    client.post(f"/api/requests/{req['id']}/schedule-pickup", headers=auth_headers(provider["token"]))

    resp = client.post(
        f"/api/requests/{req['id']}/schedule-pickup", headers=auth_headers(provider["token"])
    )
    assert resp.status_code == 409
    assert resp.get_json()["error"] == "PICKUP_ALREADY_SCHEDULED"


def test_fail_pickup_reverts_request_to_accepted(client, app):
    provider, listing, recipient, req = _accepted_request(client, app)
    pickup = client.post(
        f"/api/requests/{req['id']}/schedule-pickup", headers=auth_headers(provider["token"])
    ).get_json()["data"]

    resp = client.post(
        f"/api/pickups/{pickup['id']}/fail",
        json={"reason": "Recipient did not show up."},
        headers=auth_headers(provider["token"]),
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["status"] == "failed"

    req_after = client.get(
        f"/api/requests/{req['id']}", headers=auth_headers(recipient["token"])
    ).get_json()["data"]
    assert req_after["status"] == "accepted"

    # A new pickup can now be scheduled for the same request.
    reschedule = client.post(
        f"/api/requests/{req['id']}/schedule-pickup", headers=auth_headers(provider["token"])
    )
    assert reschedule.status_code == 201


def test_recipient_cancel_pickup_reverts_request_to_accepted(client, app):
    provider, listing, recipient, req = _accepted_request(client, app)
    pickup = client.post(
        f"/api/requests/{req['id']}/schedule-pickup", headers=auth_headers(provider["token"])
    ).get_json()["data"]

    resp = client.post(
        f"/api/pickups/{pickup['id']}/cancel", headers=auth_headers(recipient["token"])
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["status"] == "cancelled"

    req_after = client.get(
        f"/api/requests/{req['id']}", headers=auth_headers(recipient["token"])
    ).get_json()["data"]
    assert req_after["status"] == "accepted"


def test_recipient_cannot_cancel_completed_pickup(client, app):
    provider, listing, recipient, req = _accepted_request(client, app)
    pickup = client.post(
        f"/api/requests/{req['id']}/schedule-pickup",
        headers=auth_headers(provider["token"]),
    ).get_json()["data"]
    complete_resp = client.post(
        f"/api/pickups/{pickup['id']}/complete",
        headers=auth_headers(provider["token"]),
    )
    assert complete_resp.status_code == 200
    assert complete_resp.get_json()["data"]["status"] == "completed"

    cancel_resp = client.post(
        f"/api/pickups/{pickup['id']}/cancel",
        headers=auth_headers(recipient["token"]),
    )
    assert cancel_resp.status_code == 409
    assert cancel_resp.get_json()["error"] == "INVALID_PICKUP_STATE"

    pickup_after_cancel_attempt = client.get(
        f"/api/pickups/{pickup['id']}", headers=auth_headers(recipient["token"])
    ).get_json()["data"]
    assert pickup_after_cancel_attempt["status"] == "completed"


def test_only_owning_provider_can_complete_pickup(client, app):
    provider, listing, recipient, req = _accepted_request(client, app)
    pickup = client.post(
        f"/api/requests/{req['id']}/schedule-pickup", headers=auth_headers(provider["token"])
    ).get_json()["data"]

    other_provider = create_provider(client, email="not-the-owner@example.com", org_name="Other Org")
    resp = client.post(
        f"/api/pickups/{pickup['id']}/complete", headers=auth_headers(other_provider["token"])
    )
    assert resp.status_code == 403


def test_only_owning_recipient_can_confirm_pickup(client, app):
    provider, listing, recipient, req = _accepted_request(client, app)
    pickup = client.post(
        f"/api/requests/{req['id']}/schedule-pickup", headers=auth_headers(provider["token"])
    ).get_json()["data"]

    other_recipient = create_recipient(client, app, email="not-the-owner-rcpt@example.com", org_name="Other Org")
    resp = client.post(
        f"/api/pickups/{pickup['id']}/confirm", headers=auth_headers(other_recipient["token"])
    )
    assert resp.status_code == 403


def test_listing_with_two_partial_claims_needs_both_completed_to_collect(client, app):
    """
    A listing with two separately-accepted requests should only
    become COLLECTED once BOTH pickups are completed — not after the
    first one alone.
    """
    provider = create_provider(client)
    listing = create_listing(client, provider["token"], quantity=20)

    recipient_a = create_recipient(client, app, email="a@example.com", org_name="Org A")
    recipient_b = create_recipient(client, app, email="b@example.com", org_name="Org B")

    req_a = client.post(
        "/api/requests",
        json={"listing_id": listing["id"], "requested_quantity": 10},
        headers=auth_headers(recipient_a["token"]),
    ).get_json()["data"]
    req_b = client.post(
        "/api/requests",
        json={"listing_id": listing["id"], "requested_quantity": 10},
        headers=auth_headers(recipient_b["token"]),
    ).get_json()["data"]

    client.post(f"/api/requests/{req_a['id']}/accept", headers=auth_headers(provider["token"]))
    client.post(f"/api/requests/{req_b['id']}/accept", headers=auth_headers(provider["token"]))

    pickup_a = client.post(
        f"/api/requests/{req_a['id']}/schedule-pickup", headers=auth_headers(provider["token"])
    ).get_json()["data"]
    pickup_b = client.post(
        f"/api/requests/{req_b['id']}/schedule-pickup", headers=auth_headers(provider["token"])
    ).get_json()["data"]

    client.post(f"/api/pickups/{pickup_a['id']}/complete", headers=auth_headers(provider["token"]))

    still_reserved = client.get(
        f"/api/listings/{listing['id']}", headers=auth_headers(provider["token"])
    ).get_json()["data"]
    assert still_reserved["status"] == "reserved"

    client.post(f"/api/pickups/{pickup_b['id']}/complete", headers=auth_headers(provider["token"]))

    now_collected = client.get(
        f"/api/listings/{listing['id']}", headers=auth_headers(provider["token"])
    ).get_json()["data"]
    assert now_collected["status"] == "collected"


def test_distribution_record_is_visible_only_to_its_own_provider_and_recipient(client, app):
    provider, listing, recipient, req = _accepted_request(client, app)
    pickup = client.post(
        f"/api/requests/{req['id']}/schedule-pickup", headers=auth_headers(provider["token"])
    ).get_json()["data"]
    client.post(f"/api/pickups/{pickup['id']}/complete", headers=auth_headers(provider["token"]))

    distribution_id = client.get(
        "/api/distributions", headers=auth_headers(provider["token"])
    ).get_json()["data"]["distributions"][0]["id"]

    outsider = create_recipient(client, app, email="outsider@example.com", org_name="Outsider Org")
    resp = client.get(
        f"/api/distributions/{distribution_id}", headers=auth_headers(outsider["token"])
    )
    assert resp.status_code == 403
