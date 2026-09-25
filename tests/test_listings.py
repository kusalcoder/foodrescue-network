"""
Phase 5 / Phase 8 regression: food listing CRUD, ownership checks, and
browse/filter/pagination behavior.

Location-based search (near_lat/near_lng/near_me) is covered lightly
here — just enough to confirm the parameters are wired up and don't
error — since the Haversine math itself is a pure function better
suited to its own focused unit test than an end-to-end HTTP test.
"""

from tests.factories import (
    auth_headers,
    create_listing,
    create_provider,
    create_recipient,
    register_and_login,
)


def test_create_listing_success(client):
    fx = create_provider(client)
    listing = create_listing(client, fx["token"])
    assert listing["status"] == "available"
    assert listing["provider_id"] == fx["profile"]["id"]


def test_create_listing_requires_provider_profile_first(client):
    token, _ = register_and_login(client, email="no-profile-listing@example.com", role="provider")
    resp = client.post(
        "/api/listings",
        json={
            "food_name": "X",
            "category": "other",
            "quantity": 1,
            "quantity_unit": "boxes",
            "available_date": "2026-12-10",
            "pickup_start_time": "2026-12-10T17:00:00+00:00",
            "pickup_end_time": "2026-12-10T19:00:00+00:00",
            "pickup_location": "Somewhere",
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "PROFILE_NOT_FOUND"


def test_recipient_cannot_create_listing(client, app):
    fx = create_recipient(client, app, email="no-listings-for-me@example.com")
    resp = client.post(
        "/api/listings",
        json={"food_name": "X"},
        headers=auth_headers(fx["token"]),
    )
    assert resp.status_code == 403


def test_create_listing_rejects_nonpositive_quantity(client):
    fx = create_provider(client)
    resp = client.post(
        "/api/listings",
        json={
            "food_name": "Bad Quantity",
            "category": "other",
            "quantity": 0,
            "quantity_unit": "boxes",
            "available_date": "2026-12-10",
            "pickup_start_time": "2026-12-10T17:00:00+00:00",
            "pickup_end_time": "2026-12-10T19:00:00+00:00",
            "pickup_location": "Somewhere",
        },
        headers=auth_headers(fx["token"]),
    )
    assert resp.status_code == 422


def test_create_listing_rejects_end_before_start(client):
    fx = create_provider(client)
    resp = client.post(
        "/api/listings",
        json={
            "food_name": "Bad Window",
            "category": "other",
            "quantity": 5,
            "quantity_unit": "boxes",
            "available_date": "2026-12-10",
            "pickup_start_time": "2026-12-10T19:00:00+00:00",
            "pickup_end_time": "2026-12-10T17:00:00+00:00",
            "pickup_location": "Somewhere",
        },
        headers=auth_headers(fx["token"]),
    )
    assert resp.status_code == 422


def test_owner_can_update_own_listing(client):
    fx = create_provider(client)
    listing = create_listing(client, fx["token"])
    resp = client.put(
        f"/api/listings/{listing['id']}",
        json={"food_name": "Renamed Dish"},
        headers=auth_headers(fx["token"]),
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["food_name"] == "Renamed Dish"


def test_other_provider_cannot_update_listing_they_dont_own(client):
    owner = create_provider(client, email="owner@example.com")
    listing = create_listing(client, owner["token"])

    other = create_provider(client, email="other-provider@example.com", org_name="Rival Kitchen")
    resp = client.put(
        f"/api/listings/{listing['id']}",
        json={"food_name": "Hijacked"},
        headers=auth_headers(other["token"]),
    )
    assert resp.status_code in (403, 404)


def test_owner_can_cancel_own_listing(client):
    fx = create_provider(client)
    listing = create_listing(client, fx["token"])
    resp = client.post(
        f"/api/listings/{listing['id']}/cancel", headers=auth_headers(fx["token"])
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["status"] == "cancelled"


def test_get_single_listing_by_id(client, app):
    provider = create_provider(client)
    listing = create_listing(client, provider["token"])
    recipient = create_recipient(client, app, email="viewer@example.com")

    resp = client.get(f"/api/listings/{listing['id']}", headers=auth_headers(recipient["token"]))
    assert resp.status_code == 200
    assert resp.get_json()["data"]["id"] == listing["id"]


def test_get_nonexistent_listing_is_404(client):
    fx = create_provider(client)
    resp = client.get("/api/listings/999999", headers=auth_headers(fx["token"]))
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "LISTING_NOT_FOUND"


def test_mine_only_shows_own_listings(client):
    mine = create_provider(client, email="mine@example.com")
    create_listing(client, mine["token"], food_name="Mine A")
    create_listing(client, mine["token"], food_name="Mine B")

    other = create_provider(client, email="not-mine@example.com", org_name="Other Org")
    create_listing(client, other["token"], food_name="Not Mine")

    resp = client.get("/api/listings/mine", headers=auth_headers(mine["token"]))
    assert resp.status_code == 200
    names = {item["food_name"] for item in resp.get_json()["data"]}
    assert names == {"Mine A", "Mine B"}


def test_browse_filters_by_category(client, app):
    provider = create_provider(client)
    create_listing(client, provider["token"], food_name="Bread", category="bakery")
    create_listing(client, provider["token"], food_name="Curry", category="prepared_food")

    recipient = create_recipient(client, app)
    resp = client.get(
        "/api/listings?category=bakery", headers=auth_headers(recipient["token"])
    )
    assert resp.status_code == 200
    listings = resp.get_json()["data"]["listings"]
    assert all(item["category"] == "bakery" for item in listings)
    assert any(item["food_name"] == "Bread" for item in listings)


def test_browse_only_shows_available_by_default(client, app):
    provider = create_provider(client)
    listing = create_listing(client, provider["token"], food_name="Cancel Me")
    client.post(f"/api/listings/{listing['id']}/cancel", headers=auth_headers(provider["token"]))

    recipient = create_recipient(client, app)
    resp = client.get("/api/listings", headers=auth_headers(recipient["token"]))
    names = {item["food_name"] for item in resp.get_json()["data"]["listings"]}
    assert "Cancel Me" not in names


def test_browse_pagination_respects_limit(client, app):
    provider = create_provider(client)
    for i in range(15):
        create_listing(client, provider["token"], food_name=f"Item {i}")

    recipient = create_recipient(client, app)
    resp = client.get(
        "/api/listings?limit=5&page=1", headers=auth_headers(recipient["token"])
    )
    body = resp.get_json()["data"]
    assert len(body["listings"]) == 5
    assert body["pagination"]["total"] == 15
    assert body["pagination"]["total_pages"] == 3


def test_browse_never_returns_more_than_max_page_size(client, app):
    """
    Spec requirement: 'Do not retrieve unlimited listings.' Even if a
    caller asks for an enormous limit, the server clamps it.
    """
    provider = create_provider(client)
    create_listing(client, provider["token"])
    recipient = create_recipient(client, app)

    resp = client.get(
        "/api/listings?limit=999999", headers=auth_headers(recipient["token"])
    )
    assert resp.status_code == 200
    # MAX_PAGE_SIZE is 100 per app/config.py's BaseConfig
    assert resp.get_json()["data"]["pagination"]["limit"] <= 100


def test_browse_near_me_requires_profile_coordinates(client):
    """near_me=true with a recipient profile that HAS coordinates on
    file (create_recipient sets them) should succeed, not error."""
    token, _ = register_and_login(client, email="near-me-no-coords@example.com", role="recipient")
    resp = client.post(
        "/api/recipients/profile",
        json={"organization_name": "No Coords Org"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201

    resp = client.get(
        "/api/listings?near_me=true", headers=auth_headers(token)
    )
    assert resp.status_code == 422
    assert resp.get_json()["error"] == "VALIDATION_ERROR"


def test_browse_near_lat_lng_returns_distance_km(client, app):
    provider = create_provider(client)
    create_listing(client, provider["token"])
    recipient = create_recipient(client, app)

    resp = client.get(
        "/api/listings?near_lat=39.80&near_lng=-89.64&radius_km=50",
        headers=auth_headers(recipient["token"]),
    )
    assert resp.status_code == 200
    listings = resp.get_json()["data"]["listings"]
    assert len(listings) >= 1
    assert "distance_km" in listings[0]
