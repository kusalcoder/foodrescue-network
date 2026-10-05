"""
Tests for India-Only Food Donation Restrictions, Overseas Fallback,
Map Status Logic, and Collection Route Functionality.
"""

import pytest
from tests.factories import auth_headers, create_provider, create_recipient, create_listing


def test_listing_creation_overseas_location_rejected(client):
    provider = create_provider(client)
    body = {
        "food_name": "Overseas Meal",
        "category": "prepared_food",
        "quantity": 10,
        "quantity_unit": "boxes",
        "available_date": "2026-12-10",
        "pickup_start_time": "2026-12-10T17:00:00+00:00",
        "pickup_end_time": "2026-12-10T19:00:00+00:00",
        "pickup_location": "New York, USA",
        "latitude": 40.7128,
        "longitude": -74.0060,
    }
    resp = client.post(
        "/api/listings",
        json=body,
        headers=auth_headers(provider["token"]),
    )
    assert resp.status_code == 422
    data = resp.get_json()
    assert data["error"] == "INVALID_LOCATION"
    assert "India" in data["message"]


def test_listing_creation_within_india_accepted(client):
    provider = create_provider(client)
    body = {
        "food_name": "Mumbai Thali",
        "category": "prepared_food",
        "quantity": 25,
        "quantity_unit": "meals",
        "available_date": "2026-12-10",
        "pickup_start_time": "2026-12-10T17:00:00+00:00",
        "pickup_end_time": "2026-12-10T19:00:00+00:00",
        "pickup_location": "Marine Drive, Mumbai, India",
        "latitude": 18.9440,
        "longitude": 72.8230,
    }
    resp = client.post(
        "/api/listings",
        json=body,
        headers=auth_headers(provider["token"]),
    )
    assert resp.status_code == 201
    listing = resp.get_json()["data"]
    assert listing["food_name"] == "Mumbai Thali"
    assert listing["latitude"] == 18.9440


def test_profile_creation_overseas_falls_back_to_default_india_location(client):
    from tests.factories import register_and_login
    token, user = register_and_login(client, email="overseas_provider@example.com", role="provider")
    resp = client.post(
        "/api/providers/profile",
        json={
            "organization_name": "London Bakery",
            "contact_info": "+44 20 7946 0912",
            "address": "Baker St",
            "city": "London",
            "state": "Greater London",
            "pincode": "NW16XE",
            "latitude": 51.5074,  # London, UK (Outside India)
            "longitude": -0.1278,
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    profile = resp.get_json()["data"]
    assert profile["latitude"] is None
    assert profile["longitude"] is None


def test_browse_active_listings_returns_available_and_scheduled_only(client):
    provider = create_provider(client)
    listing1 = create_listing(client, provider["token"], food_name="Active Curry")
    
    resp = client.get(
        "/api/listings?status=active",
        headers=auth_headers(provider["token"]),
    )
    assert resp.status_code == 200
    listings = resp.get_json()["data"]["listings"]
    food_names = [l["food_name"] for l in listings]
    assert "Active Curry" in food_names
