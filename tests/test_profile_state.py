"""
Tests for Provider and Recipient profile state persistence and API responses.
"""

import pytest
from tests.factories import auth_headers, register_and_login


def test_provider_profile_state_creation_and_update(client):
    token, user = register_and_login(client, email="provider_state@example.com", role="provider")
    
    # 1. Create provider profile with state
    resp = client.post(
        "/api/providers/profile",
        json={
            "organization_name": "ABC Foods",
            "contact_info": "+91 9876543210",
            "address": "MG Road",
            "city": "Vijayawada",
            "state": "Andhra Pradesh",
            "pincode": "520010",
            "latitude": 16.5062,
            "longitude": 80.6480,
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert data["organization_name"] == "ABC Foods"
    assert data["state"] == "Andhra Pradesh"

    # 2. Get profile and check state
    resp_get = client.get("/api/providers/profile", headers=auth_headers(token))
    assert resp_get.status_code == 200
    assert resp_get.get_json()["data"]["state"] == "Andhra Pradesh"

    # 3. Update profile state
    resp_put = client.put(
        "/api/providers/profile",
        json={
            "organization_name": "ABC Foods",
            "state": "Telangana",
        },
        headers=auth_headers(token),
    )
    assert resp_put.status_code == 200
    assert resp_put.get_json()["data"]["state"] == "Telangana"

    # 4. Search providers by state
    resp_search = client.get("/api/providers?state=Telangana")
    assert resp_search.status_code == 200
    providers = resp_search.get_json()["data"]["providers"]
    assert len(providers) >= 1
    assert any(p["state"] == "Telangana" for p in providers)


def test_recipient_profile_state_creation_and_update(client):
    token, user = register_and_login(client, email="recipient_state@example.com", role="recipient")
    
    # 1. Create recipient profile with state
    resp = client.post(
        "/api/recipients/profile",
        json={
            "organization_name": "XYZ Orphanage",
            "contact_info": "+91 9123456789",
            "address": "Jubilee Hills",
            "city": "Hyderabad",
            "state": "Telangana",
            "pincode": "500001",
            "latitude": 17.3850,
            "longitude": 78.4867,
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert data["organization_name"] == "XYZ Orphanage"
    assert data["state"] == "Telangana"

    # 2. Search recipients by state
    resp_search = client.get("/api/recipients?state=Telangana")
    assert resp_search.status_code == 200
    recipients = resp_search.get_json()["data"]["recipients"]
    assert len(recipients) >= 1
    assert any(r["state"] == "Telangana" for r in recipients)
