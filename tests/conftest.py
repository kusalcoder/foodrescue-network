"""
Shared pytest fixtures for the whole Phase 12 suite.

Design notes (read this before adding new tests):

1. Database: every test runs against `TestingConfig`'s
   `TEST_DATABASE_URL` (see app/config.py) — NEVER the real
   development database. Tables are created once per test session
   and every table is wiped clean (not dropped) between tests, so
   each test starts from an empty database but doesn't pay the cost
   of re-running every CREATE TABLE for every single test.

2. Rate limiting: app/middleware/rate_limit.py keeps its hit-counters
   in a plain module-level dict, shared by the whole process. Left
   alone, one test's login attempts would count towards the next
   test's rate limit and cause confusing, order-dependent failures.
   The `_reset_rate_limits` autouse fixture below clears that dict
   before every single test.

3. Tokens: `generate_token()` needs an application context (it reads
   `current_app.config["SECRET_KEY"]`), so the `app` fixture pushes
   one for the whole test session rather than making every test do
   it manually.
"""

import os

# Must happen BEFORE `from app import create_app` — app/config.py
# calls load_dotenv() and reads FLASK_ENV at import time.
os.environ["FLASK_ENV"] = "testing"

import pytest

from app import create_app
from app.extensions import db as _db
from app.middleware import rate_limit as rate_limit_module


@pytest.fixture(scope="session")
def app():
    """
    One Flask app, built with TestingConfig, for the whole test run.

    TestingConfig.SQLALCHEMY_DATABASE_URI comes from TEST_DATABASE_URL
    (see app/config.py) — if that isn't set, it silently falls back to
    the real DATABASE_URL, which would mean tests run against your
    real data. `_assert_using_test_database` below fails loudly
    instead of letting that happen quietly.
    """
    flask_app = create_app("testing")
    _assert_using_test_database(flask_app)

    ctx = flask_app.app_context()
    ctx.push()

    _db.drop_all()
    _db.create_all()

    yield flask_app

    _db.session.remove()
    _db.drop_all()
    _db.engine.dispose()
    ctx.pop()


def _assert_using_test_database(flask_app):
    uri = flask_app.config.get("SQLALCHEMY_DATABASE_URI") or ""
    if "test" not in uri.lower():
        raise RuntimeError(
            "Refusing to run tests: SQLALCHEMY_DATABASE_URI does not look "
            "like a test database (expected the database name to contain "
            "'test'). Got: "
            f"{uri!r}. Set TEST_DATABASE_URL in your .env to a database "
            "you're comfortable wiping between every test run — see "
            "PHASE12_SETUP.md."
        )


@pytest.fixture()
def client(app):
    """A fresh Flask test client for each test."""
    return app.test_client()


@pytest.fixture(autouse=True)
def _clean_database(app):
    """
    Wipe every table after each test, in FK-safe order, so tests never
    see leftover rows from a previous test. Runs AFTER the test (not
    before) so a failed test leaves the database inspectable if you
    want to poke at it manually before running the next test.
    """
    yield
    with app.app_context():
        _db.session.rollback()
        for table in reversed(_db.metadata.sorted_tables):
            _db.session.execute(table.delete())
        _db.session.commit()


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """
    Clear the in-memory rate-limit counters before every test so
    tests don't interfere with each other's login/register attempt
    counts. See app/middleware/rate_limit.py.
    """
    rate_limit_module._hits.clear()
    yield
    rate_limit_module._hits.clear()


@pytest.fixture()
def db_session(app):
    """Convenience accessor for tests that need to read/write the
    database directly (e.g. asserting on an AuditLog row, or setting
    up state that has no API endpoint of its own)."""
    return _db.session
