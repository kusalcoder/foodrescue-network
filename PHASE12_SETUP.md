# Phase 12 Setup — Automated Testing

This adds a `pytest` test suite under `tests/`, covering every phase's
core behavior end-to-end, role-based access control, and the two
things a manual Postman walkthrough can't really prove on its own:
rate-limit *counts* (exactly 10, exactly 5) and the row-lock
concurrency guarantee from Phase 6.

## 1. Copy these files into your project

Unzip this package's contents directly into your project folder
(`...\foodrescue_network_phase11\foodrescue_network\`), so you end up
with:

```
foodrescue_network/
├── app/                    (already there — untouched)
├── tests/                  <- NEW
│   ├── __init__.py
│   ├── conftest.py
│   ├── factories.py
│   ├── test_auth.py
│   ├── test_profiles.py
│   ├── test_listings.py
│   ├── test_requests.py
│   ├── test_pickups_and_distributions.py
│   ├── test_notifications.py
│   ├── test_admin_and_audit.py
│   ├── test_reports.py
│   ├── test_rate_limiting.py
│   └── test_concurrency.py
├── pytest.ini              <- NEW
├── requirements-test.txt   <- NEW
├── run.py                  (already there)
└── .env                    (already there — you'll add ONE line, see step 3)
```

Nothing here touches `app/` — the test suite only calls your existing
code through its public functions and HTTP routes.

## 2. Create a real test database

Your `.env` already has a line for this, but with a placeholder
password that won't work:

```
TEST_DATABASE_URL=postgresql://foodrescue_user:replace_with_password@localhost:5432/foodrescue_test_db
```

Simplest fix: reuse the same working credentials your main database
already uses (`postgres` / `root`, per your current `.env`), just
pointing at a **different database name** so tests can never touch
your real data:

**Step 2a — create the database.** In a terminal:
```
"C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h localhost -p 5432 -c "CREATE DATABASE foodrescue_test_db;"
```
(Type your Postgres password — `root` — when prompted.)

**Step 2b — update `.env`.** Change that one line to:
```
TEST_DATABASE_URL=postgresql://postgres:root@localhost:5432/foodrescue_test_db
```

`tests/conftest.py` refuses to run at all if the resolved database
URL doesn't have "test" in its name — this is a deliberate safety
check so a typo here can never accidentally point the test suite (which
**deletes every row after every single test**) at your real
`foodrescue_db`.

## 3. Install test dependencies

```
cd C:\Users\Admin\Downloads\project\foodrescue_network_phase11\foodrescue_network
..\..\venv\Scripts\activate
pip install -r requirements-test.txt --break-system-packages
```
(Drop `--break-system-packages` if pip complains about it on Windows —
it's mainly needed on Linux-style "externally managed" Python installs.)

## 4. Run the suite

With the venv active, from the same folder:

```
pytest
```

You do **not** need `python run.py` running in another window — these
tests call your Flask app directly in-process via its test client,
never over a real HTTP port. That also means the port-5000/stale-process
issues from Phase 11 testing simply can't happen here.

Useful variations:
```
pytest -v                        # verbose, one line per test
pytest tests/test_requests.py    # just one file
pytest -m "not slow"             # skip rate-limit tests (they run ~10-15 real requests each)
pytest -k concurrency            # just the concurrency test
```

## 5. What "done" looks like

Every test should pass. If something fails, pytest prints the exact
assertion that broke and the actual vs. expected values — that's
usually enough to tell you whether the test's expectation is wrong
(unlikely, given it was built directly against your Phase 1-11 code)
or whether a real regression crept in.

## Notes on what's covered vs. not

- **Full lifecycle**: `test_pickups_and_distributions.py::test_full_lifecycle_register_to_distribution`
  walks register → profile → listing → request → accept → schedule →
  confirm → complete → distribution record, in one continuous test.
- **RBAC**: every route with a `@role_required` gets at least one
  "wrong role gets 403" test, spread across the relevant file for
  that resource rather than collected in one giant file.
- **Concurrency**: `test_concurrency.py` uses two real OS threads to
  race two `accept_request` calls against the same listing, proving
  the `with_for_update()` row lock actually prevents double-allocation
  — not just that the code *looks* correct.
- **Rate limiting**: `test_rate_limiting.py` hits the real configured
  limits (10 login attempts, 5 registrations) rather than a mocked
  smaller number, so a change to those production constants is
  exactly what would break this test.
- **Not covered in depth**: the Haversine distance math in
  `app/utils/geo.py` and `app/services/geo_search_service.py` gets
  light smoke-testing (does `near_lat`/`near_lng` return a
  `distance_km` field at all) rather than exhaustive numeric
  verification — that's a good candidate to add unit tests for later
  if you want tighter coverage there.
