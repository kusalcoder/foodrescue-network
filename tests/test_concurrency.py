"""
Phase 6 regression: the concurrency guarantee described in
app/services/request_service.py's module docstring.

Two recipients each submit a PENDING request against the same
listing, together asking for more than the listing actually has
available. Both requests are allowed to sit PENDING at once (spec
section 15). The provider then tries to ACCEPT both at almost exactly
the same instant, from two real OS threads — this is the only way to
actually exercise `with_for_update()`'s row lock, rather than just
trusting that the code that calls it is correct.

Exactly one accept must succeed; the other must fail with
QUANTITY_EXCEEDS_AVAILABLE — never both succeeding (which would mean
the listing "gave away" more food than it had), and never both
failing (which would mean the lock is starving every caller).

Each thread pushes its OWN Flask application context. Flask-SQLAlchemy's
`db.session` is a scoped session keyed by that context, so this gives
each thread its own independent DB session/connection — mirroring how
two real concurrent HTTP requests would each get their own session in
a real multi-threaded WSGI server.
"""

import threading

import pytest

from app.extensions import db
from app.models import ProviderProfile
from app.services.request_service import RequestError, accept_request
from tests.factories import auth_headers, create_listing, create_provider, create_recipient

pytestmark = pytest.mark.concurrency


def test_concurrent_accept_never_double_allocates_a_listing(client, app):
    provider = create_provider(client)
    listing = create_listing(client, provider["token"], quantity=10)

    recipient_a = create_recipient(client, app, email="race-a@example.com", org_name="Org A")
    recipient_b = create_recipient(client, app, email="race-b@example.com", org_name="Org B")

    # Each request alone fits (8 <= 10), but the two TOGETHER (16)
    # exceed the listing's quantity — exactly the scenario the row
    # lock exists to protect against.
    req_a = client.post(
        "/api/requests",
        json={"listing_id": listing["id"], "requested_quantity": 8},
        headers=auth_headers(recipient_a["token"]),
    ).get_json()["data"]
    req_b = client.post(
        "/api/requests",
        json={"listing_id": listing["id"], "requested_quantity": 8},
        headers=auth_headers(recipient_b["token"]),
    ).get_json()["data"]

    provider_profile_id = provider["profile"]["id"]
    barrier = threading.Barrier(2)
    results = {}

    def worker(request_id, label):
        with app.app_context():
            barrier.wait(timeout=5)  # line both threads up before either commits
            fresh_provider_profile = db.session.get(ProviderProfile, provider_profile_id)
            try:
                accept_request(request_id=request_id, provider_profile=fresh_provider_profile)
                results[label] = "ok"
            except RequestError as exc:
                results[label] = exc.error_code
            finally:
                db.session.remove()

    thread_a = threading.Thread(target=worker, args=(req_a["id"], "a"))
    thread_b = threading.Thread(target=worker, args=(req_b["id"], "b"))
    thread_a.start()
    thread_b.start()
    thread_a.join(timeout=10)
    thread_b.join(timeout=10)

    outcomes = sorted(results.values())
    assert outcomes == ["QUANTITY_EXCEEDS_AVAILABLE", "ok"], (
        f"expected exactly one success and one quantity-exceeded rejection, got {results}"
    )

    # Confirm the database agrees: only ONE of the two requests ended
    # up ACCEPTED, never both.
    req_a_after = client.get(
        f"/api/requests/{req_a['id']}", headers=auth_headers(provider["token"])
    ).get_json()["data"]
    req_b_after = client.get(
        f"/api/requests/{req_b['id']}", headers=auth_headers(provider["token"])
    ).get_json()["data"]

    accepted_count = sum(
        1 for r in (req_a_after, req_b_after) if r["status"] == "accepted"
    )
    assert accepted_count == 1
