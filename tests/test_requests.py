"""
Phase 6 regression: the request workflow, quantity-safety rules, and
resource-level authorization (spec sections 13-15, 34-36).

Concurrency (the row-lock guarantee at accept-time) has its own
dedicated, more elaborate test in test_concurrency.py.
"""

from tests.factories import (
    auth_headers,
    create_listing,
    create_provider,
    create_recipient,
)


def _setup(client, app, quantity=50):
    provider = create_provider(client)
    listing = create_listing(client, provider["token"], quantity=quantity)
    recipient = create_recipient(client, app)
    return provider, listing, recipient


def test_unverified_recipient_cannot_request(client, app):
    provider = create_provider(client)
    listing = create_listing(client, provider["token"])
    unverified = create_recipient(client, app, email="unverified@example.com", verified=False)

    resp = client.post(
        "/api/requests",
        json={"listing_id": listing["id"], "requested_quantity": 5},
        headers=auth_headers(unverified["token"]),
    )
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "RECIPIENT_NOT_VERIFIED"


def test_verified_recipient_can_request(client, app):
    _, listing, recipient = _setup(client, app)
    resp = client.post(
        "/api/requests",
        json={"listing_id": listing["id"], "requested_quantity": 10, "request_message": "Please"},
        headers=auth_headers(recipient["token"]),
    )
    assert resp.status_code == 201
    assert resp.get_json()["data"]["status"] == "pending"


def test_request_rejects_nonexistent_listing(client, app):
    _, _, recipient = _setup(client, app)
    resp = client.post(
        "/api/requests",
        json={"listing_id": 999999, "requested_quantity": 5},
        headers=auth_headers(recipient["token"]),
    )
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "LISTING_NOT_FOUND"


def test_request_rejects_quantity_exceeding_available(client, app):
    _, listing, recipient = _setup(client, app, quantity=10)
    resp = client.post(
        "/api/requests",
        json={"listing_id": listing["id"], "requested_quantity": 999},
        headers=auth_headers(recipient["token"]),
    )
    assert resp.status_code == 409
    assert resp.get_json()["error"] == "QUANTITY_EXCEEDS_AVAILABLE"


def test_request_rejects_nonpositive_quantity(client, app):
    _, listing, recipient = _setup(client, app)
    resp = client.post(
        "/api/requests",
        json={"listing_id": listing["id"], "requested_quantity": 0},
        headers=auth_headers(recipient["token"]),
    )
    assert resp.status_code == 422


def test_duplicate_active_request_is_rejected(client, app):
    _, listing, recipient = _setup(client, app)
    client.post(
        "/api/requests",
        json={"listing_id": listing["id"], "requested_quantity": 5},
        headers=auth_headers(recipient["token"]),
    )
    resp = client.post(
        "/api/requests",
        json={"listing_id": listing["id"], "requested_quantity": 5},
        headers=auth_headers(recipient["token"]),
    )
    assert resp.status_code == 409
    assert resp.get_json()["error"] == "DUPLICATE_REQUEST"


def test_two_different_recipients_can_have_overlapping_pending_requests(client, app):
    """
    Spec section 15's own example: multiple PENDING requests against
    the same listing are allowed even if their quantities overlap —
    the hard guarantee only applies at ACCEPT time.
    """
    provider = create_provider(client)
    listing = create_listing(client, provider["token"], quantity=10)

    recipient_a = create_recipient(client, app, email="a@example.com", org_name="Org A")
    recipient_b = create_recipient(client, app, email="b@example.com", org_name="Org B")

    resp_a = client.post(
        "/api/requests",
        json={"listing_id": listing["id"], "requested_quantity": 8},
        headers=auth_headers(recipient_a["token"]),
    )
    resp_b = client.post(
        "/api/requests",
        json={"listing_id": listing["id"], "requested_quantity": 8},
        headers=auth_headers(recipient_b["token"]),
    )
    assert resp_a.status_code == 201
    assert resp_b.status_code == 201  # both pending is fine


def test_accept_request_updates_status_and_notifies(client, app):
    provider, listing, recipient = _setup(client, app)
    req = client.post(
        "/api/requests",
        json={"listing_id": listing["id"], "requested_quantity": 10},
        headers=auth_headers(recipient["token"]),
    ).get_json()["data"]

    resp = client.post(
        f"/api/requests/{req['id']}/accept", headers=auth_headers(provider["token"])
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["status"] == "accepted"

    notif_resp = client.get(
        "/api/notifications", headers=auth_headers(recipient["token"])
    )
    types = {n["notification_type"] for n in notif_resp.get_json()["data"]["notifications"]}
    assert "request_accepted" in types


def test_accepting_full_quantity_reserves_the_listing(client, app):
    provider, listing, recipient = _setup(client, app, quantity=10)
    req = client.post(
        "/api/requests",
        json={"listing_id": listing["id"], "requested_quantity": 10},
        headers=auth_headers(recipient["token"]),
    ).get_json()["data"]

    client.post(f"/api/requests/{req['id']}/accept", headers=auth_headers(provider["token"]))

    listing_resp = client.get(
        f"/api/listings/{listing['id']}", headers=auth_headers(provider["token"])
    )
    assert listing_resp.get_json()["data"]["status"] == "reserved"


def test_non_owning_provider_cannot_accept_request(client, app):
    provider, listing, recipient = _setup(client, app)
    req = client.post(
        "/api/requests",
        json={"listing_id": listing["id"], "requested_quantity": 5},
        headers=auth_headers(recipient["token"]),
    ).get_json()["data"]

    other_provider = create_provider(client, email="rival@example.com", org_name="Rival Kitchen")
    resp = client.post(
        f"/api/requests/{req['id']}/accept", headers=auth_headers(other_provider["token"])
    )
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "FORBIDDEN"


def test_cannot_accept_already_accepted_request(client, app):
    provider, listing, recipient = _setup(client, app)
    req = client.post(
        "/api/requests",
        json={"listing_id": listing["id"], "requested_quantity": 5},
        headers=auth_headers(recipient["token"]),
    ).get_json()["data"]

    client.post(f"/api/requests/{req['id']}/accept", headers=auth_headers(provider["token"]))
    resp = client.post(f"/api/requests/{req['id']}/accept", headers=auth_headers(provider["token"]))
    assert resp.status_code == 409
    assert resp.get_json()["error"] == "INVALID_REQUEST_STATE"


def test_reject_request(client, app):
    provider, listing, recipient = _setup(client, app)
    req = client.post(
        "/api/requests",
        json={"listing_id": listing["id"], "requested_quantity": 5},
        headers=auth_headers(recipient["token"]),
    ).get_json()["data"]

    resp = client.post(f"/api/requests/{req['id']}/reject", headers=auth_headers(provider["token"]))
    assert resp.status_code == 200
    assert resp.get_json()["data"]["status"] == "rejected"


def test_recipient_can_cancel_own_pending_request(client, app):
    _, listing, recipient = _setup(client, app)
    req = client.post(
        "/api/requests",
        json={"listing_id": listing["id"], "requested_quantity": 5},
        headers=auth_headers(recipient["token"]),
    ).get_json()["data"]

    resp = client.post(f"/api/requests/{req['id']}/cancel", headers=auth_headers(recipient["token"]))
    assert resp.status_code == 200
    assert resp.get_json()["data"]["status"] == "cancelled"


def test_cancelling_accepted_request_frees_up_listing(client, app):
    provider, listing, recipient = _setup(client, app, quantity=10)
    req = client.post(
        "/api/requests",
        json={"listing_id": listing["id"], "requested_quantity": 10},
        headers=auth_headers(recipient["token"]),
    ).get_json()["data"]

    client.post(f"/api/requests/{req['id']}/accept", headers=auth_headers(provider["token"]))
    listing_after_accept = client.get(
        f"/api/listings/{listing['id']}", headers=auth_headers(provider["token"])
    ).get_json()["data"]
    assert listing_after_accept["status"] == "reserved"

    client.post(f"/api/requests/{req['id']}/cancel", headers=auth_headers(recipient["token"]))
    listing_after_cancel = client.get(
        f"/api/listings/{listing['id']}", headers=auth_headers(provider["token"])
    ).get_json()["data"]
    assert listing_after_cancel["status"] == "available"


def test_other_recipient_cannot_cancel_someone_elses_request(client, app):
    _, listing, recipient = _setup(client, app)
    req = client.post(
        "/api/requests",
        json={"listing_id": listing["id"], "requested_quantity": 5},
        headers=auth_headers(recipient["token"]),
    ).get_json()["data"]

    other_recipient = create_recipient(client, app, email="other-rcpt@example.com", org_name="Other Org")
    resp = client.post(
        f"/api/requests/{req['id']}/cancel", headers=auth_headers(other_recipient["token"])
    )
    assert resp.status_code == 403


def test_get_request_visible_to_owning_recipient_and_provider_only(client, app):
    provider, listing, recipient = _setup(client, app)
    req = client.post(
        "/api/requests",
        json={"listing_id": listing["id"], "requested_quantity": 5},
        headers=auth_headers(recipient["token"]),
    ).get_json()["data"]

    assert client.get(f"/api/requests/{req['id']}", headers=auth_headers(recipient["token"])).status_code == 200
    assert client.get(f"/api/requests/{req['id']}", headers=auth_headers(provider["token"])).status_code == 200

    stranger = create_recipient(client, app, email="stranger@example.com", org_name="Stranger Org")
    resp = client.get(f"/api/requests/{req['id']}", headers=auth_headers(stranger["token"]))
    assert resp.status_code == 403


def test_requests_for_listing_endpoint_is_owner_only(client, app):
    provider, listing, recipient = _setup(client, app)
    client.post(
        "/api/requests",
        json={"listing_id": listing["id"], "requested_quantity": 5},
        headers=auth_headers(recipient["token"]),
    )

    ok = client.get(
        f"/api/listings/{listing['id']}/requests", headers=auth_headers(provider["token"])
    )
    assert ok.status_code == 200
    assert len(ok.get_json()["data"]) == 1

    other_provider = create_provider(client, email="not-the-owner@example.com", org_name="Other Org")
    forbidden = client.get(
        f"/api/listings/{listing['id']}/requests", headers=auth_headers(other_provider["token"])
    )
    assert forbidden.status_code == 403
