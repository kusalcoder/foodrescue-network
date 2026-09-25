"""
Reusable test-data helpers.

These deliberately go through the real HTTP API (`client.post(...)`)
wherever a route already exists for the action, rather than poking
the database directly — that way every fixture doubles as extra
coverage of the registration/profile-creation endpoints, and fixtures
can never drift out of sync with real request/response shapes.

The one exception is recipient verification: going through the admin
API for that in every fixture that needs a verified recipient would
mean every such fixture also depends on an admin token, which adds
noise to tests that have nothing to do with admin behavior. Instead
`verify_recipient_directly()` flips the flag straight in the
database. `test_admin_and_audit.py` still tests the real
POST /api/recipients/<id>/verify endpoint explicitly.
"""

from app.extensions import db
from app.models import RecipientProfile, VerificationStatus

DEFAULT_PASSWORD = "SecurePass123"


def register(client, *, email, role, name=None, password=DEFAULT_PASSWORD):
    """POST /api/auth/register. Returns the parsed JSON body."""
    resp = client.post(
        "/api/auth/register",
        json={
            "name": name or f"{role.title()} Test User",
            "email": email,
            "password": password,
            "role": role,
        },
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["data"]


def login(client, *, email, password=DEFAULT_PASSWORD):
    """POST /api/auth/login. Returns (token, user_dict)."""
    resp = client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()["data"]
    return body["token"], body["user"]


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def register_and_login(client, *, email, role, name=None, password=DEFAULT_PASSWORD):
    """Register + log in in one step. Returns (token, user_dict)."""
    register(client, email=email, role=role, name=name, password=password)
    return login(client, email=email, password=password)


def make_admin(app):
    """
    Create an ADMIN user directly in the database.

    There is no public "become an admin" endpoint by design (spec:
    "Normal registration must not allow users to create administrator
    accounts themselves") — so a real deployment's first admin has to
    be created by some out-of-band means, and tests mirror that here.
    """
    from app.auth.security import hash_password
    from app.models import AccountStatus, User, UserRole

    with app.app_context():
        admin = User(
            name="Site Admin",
            email="admin-fixture@example.com",
            password_hash=hash_password(DEFAULT_PASSWORD),
            role=UserRole.ADMIN,
            status=AccountStatus.ACTIVE,
        )
        db.session.add(admin)
        db.session.commit()
        return admin.id, admin.email


def make_admin_token(client, app):
    """Create an admin and return (token, user_id)."""
    _, email = make_admin(app)
    token, user = login(client, email=email)
    return token, user["id"]


def create_provider(client, *, email="provider@example.com", org_name="Green Table Restaurant"):
    """
    Register + log in a PROVIDER and give them a completed provider
    profile. Returns a dict: {token, user, profile}.
    """
    token, user = register_and_login(client, email=email, role="provider")
    resp = client.post(
        "/api/providers/profile",
        json={
            "organization_name": org_name,
            "contact_info": "+1 555-0100",
            "address": "12 Market St",
            "city": "Springfield",
            "latitude": 39.799999,
            "longitude": -89.644444,
            "description": "Test fixture provider.",
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.get_json()
    return {"token": token, "user": user, "profile": resp.get_json()["data"]}


def create_recipient(
    client, app, *, email="recipient@example.com", org_name="Hope Community Shelter", verified=True
):
    """
    Register + log in a RECIPIENT and give them a completed recipient
    profile. Verified by default (bypassing the admin endpoint — see
    module docstring) since most fixtures that need a recipient at
    all also need that recipient able to place requests.
    """
    token, user = register_and_login(client, email=email, role="recipient")
    resp = client.post(
        "/api/recipients/profile",
        json={
            "organization_name": org_name,
            "contact_info": "+1 555-0200",
            "address": "88 Elm St",
            "city": "Springfield",
            "latitude": 39.801,
            "longitude": -89.650,
            "description": "Test fixture recipient.",
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.get_json()
    profile = resp.get_json()["data"]

    if verified:
        verify_recipient_directly(app, profile_id=profile["id"])
        profile["verification_status"] = "verified"

    return {"token": token, "user": user, "profile": profile}


def verify_recipient_directly(app, *, profile_id):
    with app.app_context():
        profile = db.session.get(RecipientProfile, profile_id)
        profile.verification_status = VerificationStatus.VERIFIED
        db.session.commit()


def create_listing(client, provider_token, **overrides):
    """
    POST /api/listings as the given provider. Sensible defaults for
    every required field; pass keyword args to override any of them.
    Returns the parsed listing dict.
    """
    body = {
        "food_name": "Vegetable Biryani",
        "description": "Freshly cooked, from tonight's event.",
        "category": "prepared_food",
        "quantity": 50,
        "quantity_unit": "meals",
        "available_date": "2026-12-10",
        "pickup_start_time": "2026-12-10T17:00:00+00:00",
        "pickup_end_time": "2026-12-10T19:00:00+00:00",
        "pickup_location": "12 Market St, Springfield",
        "latitude": 39.799999,
        "longitude": -89.644444,
        "conditions": "Pickup only. Keep refrigerated.",
    }
    body.update(overrides)
    resp = client.post(
        "/api/listings", json=body, headers=auth_headers(provider_token)
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["data"]


def create_request(client, recipient_token, *, listing_id, quantity=10, message=None):
    resp = client.post(
        "/api/requests",
        json={
            "listing_id": listing_id,
            "requested_quantity": quantity,
            "request_message": message or "We can pick up any time after 5pm.",
        },
        headers=auth_headers(recipient_token),
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["data"]
