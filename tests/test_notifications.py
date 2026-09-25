"""
Phase 9 regression: in-app notifications.

The event-triggering behavior itself (e.g. "accepting a request
notifies the recipient") is exercised in test_requests.py and
test_pickups_and_distributions.py, right alongside the state change
that causes it — that's deliberate, so a broken notification shows up
next to the workflow step that broke it. This file focuses on the
notification-list/mark-read endpoints themselves.
"""

from tests.factories import auth_headers, create_listing, create_provider, create_recipient


def test_new_notification_is_unread_by_default(client, app):
    provider = create_provider(client)
    listing = create_listing(client, provider["token"])
    recipient = create_recipient(client, app)

    client.post(
        "/api/requests",
        json={"listing_id": listing["id"], "requested_quantity": 5},
        headers=auth_headers(recipient["token"]),
    )

    resp = client.get("/api/notifications", headers=auth_headers(provider["token"]))
    body = resp.get_json()["data"]
    assert body["unread_count"] >= 1
    assert all(
        n["is_read"] is False
        for n in body["notifications"]
        if n["notification_type"] == "request_received"
    )


def test_mark_notification_read_is_idempotent(client, app):
    provider = create_provider(client)
    listing = create_listing(client, provider["token"])
    recipient = create_recipient(client, app)
    client.post(
        "/api/requests",
        json={"listing_id": listing["id"], "requested_quantity": 5},
        headers=auth_headers(recipient["token"]),
    )

    notif_id = client.get(
        "/api/notifications", headers=auth_headers(provider["token"])
    ).get_json()["data"]["notifications"][0]["id"]

    first = client.post(
        f"/api/notifications/{notif_id}/read", headers=auth_headers(provider["token"])
    )
    assert first.status_code == 200
    assert first.get_json()["data"]["is_read"] is True

    second = client.post(
        f"/api/notifications/{notif_id}/read", headers=auth_headers(provider["token"])
    )
    assert second.status_code == 200  # not an error the second time


def test_unread_only_filter(client, app):
    provider = create_provider(client)
    listing = create_listing(client, provider["token"])
    recipient = create_recipient(client, app)
    client.post(
        "/api/requests",
        json={"listing_id": listing["id"], "requested_quantity": 5},
        headers=auth_headers(recipient["token"]),
    )

    notif_id = client.get(
        "/api/notifications", headers=auth_headers(provider["token"])
    ).get_json()["data"]["notifications"][0]["id"]
    client.post(f"/api/notifications/{notif_id}/read", headers=auth_headers(provider["token"]))

    resp = client.get(
        "/api/notifications?unread_only=true", headers=auth_headers(provider["token"])
    )
    ids = {n["id"] for n in resp.get_json()["data"]["notifications"]}
    assert notif_id not in ids


def test_cannot_mark_someone_elses_notification_read(client, app):
    provider = create_provider(client)
    listing = create_listing(client, provider["token"])
    recipient = create_recipient(client, app)
    client.post(
        "/api/requests",
        json={"listing_id": listing["id"], "requested_quantity": 5},
        headers=auth_headers(recipient["token"]),
    )

    notif_id = client.get(
        "/api/notifications", headers=auth_headers(provider["token"])
    ).get_json()["data"]["notifications"][0]["id"]

    resp = client.post(
        f"/api/notifications/{notif_id}/read", headers=auth_headers(recipient["token"])
    )
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "FORBIDDEN"
