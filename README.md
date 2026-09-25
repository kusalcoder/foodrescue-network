# FoodRescue Network — Backend API

A backend-only REST API for coordinating surplus food redistribution
between **Providers** (restaurants, event organizers, etc.),
**Recipient Organizations**, and platform **Administrators**.

Built with **Python + Flask + PostgreSQL**. This is a long-term,
multi-phase academic project — this README will grow as each phase
is completed.

> **Important:** FoodRescue Network is a *coordination platform*. It
> stores and displays information supplied by providers (e.g. "keep
> refrigerated"). It does **not** certify food as safe, and makes no
> medical, nutritional, or food-safety guarantees.

---

## Project Status: Phase 11 — Security and Audit ✅

Phase 6 lets verified recipients request food from listings, and lets
providers accept or reject those requests — with quantity-safety
guarantees enforced at the database level so two recipients can never
successfully claim more food than a listing actually has.

### What's included in Phase 6

- `app/services/request_service.py` — the full request lifecycle:
  - `create_request` — recipient submits a request (checks listing is
    available, not expired, has enough remaining quantity, and blocks
    duplicate active requests on the same listing)
  - `accept_request` — provider accepts (uses `SELECT ... FOR UPDATE`
    to **lock the listing row**, so two simultaneous "accept" calls on
    the same listing can never both succeed if that would overcommit
    the quantity — spec section 35's concurrency requirement)
  - `reject_request` / `cancel_request` — with correct status-transition
    rules (only `pending` requests can be rejected; `pending` or
    `accepted` requests can be cancelled, correctly freeing up quantity)
- `app/routes/requests.py`:
  - `POST /api/requests` — submit a request
  - `GET /api/requests` — my own requests (recipient)
  - `GET /api/requests/<id>` — view one (owning recipient OR owning provider)
  - `POST /api/requests/<id>/accept` / `/reject` / `/cancel`
- `GET /api/listings/<id>/requests` — all requests for a listing (provider,
  must own it)
- **Minimal admin action, pulled forward from the full Administrator
  module**: `POST /api/recipients/<id>/verify` — spec section 7 requires
  recipients be verified before requesting food, so Phase 6 can't be
  tested without *some* way to flip that flag. The complete
  Administrator module (user management, account activation, audit
  log access) is still built later.

**Quantity math:** a listing's `quantity` field never changes.
"Remaining" is always computed as `quantity - SUM(requested_quantity
of ACCEPTED requests)`. Submitting a request only checks this
loosely (multiple recipients can have overlapping pending requests,
matching spec section 15's own example); the **hard** guarantee is
enforced only at accept-time, under a row lock.

### What's included in Phase 7

Phase 7 picks up exactly where Phase 6 stopped: an `ACCEPTED` request
could never move any further. Phase 7 adds the last two steps of the
lifecycle:

```text
ACCEPTED -> PICKUP_PENDING -> COMPLETED
```

- `app/services/pickup_service.py` — pickup scheduling and its own
  independent lifecycle:
  - `schedule_pickup` — provider schedules a pickup for a request
    they've accepted (creates a `PickupRecord`, moves the request to
    `pickup_pending`)
  - `confirm_pickup` — recipient confirms a scheduled pickup
  - `complete_pickup` — provider marks the handover as having
    actually happened; this is the **only** place in the whole system
    that creates a `DistributionRecord` — the permanent, append-only
    proof that food changed hands. It also moves the request to
    `completed`, and flips the listing to `collected` once every
    claim against it has been picked up (a listing can have several
    concurrently accepted requests, per spec section 15, so one
    completed pickup shouldn't prematurely close out the others)
  - `fail_pickup` — provider marks a no-show; the request reverts to
    `accepted` so a new pickup can be scheduled
  - `cancel_pickup` — recipient cancels a pickup they can't make;
    same revert-to-`accepted` behavior
- `app/services/distribution_service.py` — read-only history queries.
  There is deliberately no create/update/delete here — every
  `DistributionRecord` is written exactly once, inside
  `complete_pickup`'s transaction, and treated as permanent after
  that (spec section 17 / rule #6 — "Completed distributions cannot
  be arbitrarily changed").
- `app/routes/requests.py`:
  - `POST /api/requests/<id>/schedule-pickup` — provider schedules a
    pickup for an accepted request (registered here, not on
    `pickups_bp`, since the resource in the URL is still a request)
- `app/routes/pickups.py`:
  - `GET /api/pickups` — every pickup involving me (provider or
    recipient), paginated
  - `GET /api/pickups/<id>` — view one (owning provider OR owning
    recipient)
  - `POST /api/pickups/<id>/confirm` — recipient confirms
  - `POST /api/pickups/<id>/complete` — provider completes
  - `POST /api/pickups/<id>/fail` — provider marks failed
  - `POST /api/pickups/<id>/cancel` — recipient cancels
- `app/routes/distributions.py`:
  - `GET /api/distributions` — my distribution history (provider or
    recipient), paginated
  - `GET /api/distributions/<id>` — view one (owning provider OR
    owning recipient)

**Pickup lifecycle** (independent of the request's own status):

```text
SCHEDULED -> CONFIRMED -> COMPLETED
          \-> FAILED
          \-> CANCELLED
```

**No new dependencies or migrations are needed for Phase 7** — the
`pickup_records` and `distribution_records` tables (and their
`PickupStatus` enum) were already created back in Phase 2's initial
migration, in anticipation of this phase.

### What's included in Phase 8

Phase 8 adds location-based search on top of the `latitude`/
`longitude` columns every profile and listing already had from
Phase 2 onward — no new dependencies, no new tables, no migration.
Distance is computed with the Haversine formula (`app/utils/geo.py`)
rather than a spatial database extension, which is accurate enough at
city/regional scale and keeps the project dependency-free.

- `app/utils/geo.py` — `haversine_km(lat1, lon1, lat2, lon2)` (great
  circle distance, in km) plus shared validators: `validate_lat_lng`
  (a coordinate pair must be supplied together and be in-range) and
  `validate_radius_km` (defaults to 25 km, capped at 500 km).
- `app/services/listing_service.py` — new `browse_listings_within_radius`:
  takes the same filtered-but-not-yet-paginated query
  `browse_listings_query` already built (status/category/city/etc.),
  drops listings with no coordinates or outside the radius, sorts
  nearest-first, and paginates the filtered result.
- `app/services/geo_search_service.py` (new file) — the
  profile-to-profile searches:
  - `nearest_verified_recipients` — verified recipients within a
    radius, nearest first
  - `nearest_providers_with_availability` — providers who currently
    have at least one `available` listing, within a radius, nearest
    first
- `app/routes/listings.py` — `GET /api/listings` gains optional
  `near_lat` + `near_lng` (must be supplied together), `near_me=true`
  (uses the caller's own provider/recipient profile coordinates
  instead), and `radius_km`. When a location search is active, every
  listing in the response gets a `distance_km` field and results are
  ordered nearest-first instead of newest-first.
- `app/routes/providers.py` — `GET /api/providers/nearby-recipients`
  (provider only): nearest verified recipient organizations to MY
  provider profile — e.g. to proactively reach out about a big
  surplus.
- `app/routes/recipients.py` — `GET /api/recipients/nearby-providers`
  (recipient only): nearest providers to MY recipient profile that
  currently have food available.

**No new dependencies or migrations are needed for Phase 8** — it
only adds routes and business logic on top of the `latitude`/
`longitude` columns that already existed on every profile and listing.

### What's included in Phase 9

Phase 9 wires up the `Notification` model that's been sitting
scaffolded since Phase 2 into the lifecycle events from every prior
phase. It's in-app only for this phase — no email/SMS provider — so
a notification is just a row a user can fetch with `GET
/api/notifications` and mark as read; there's no push delivery.

- `app/services/notification_service.py` (new file):
  - `create_notification` — stages a new notification row. It
    deliberately does **not** call `db.session.commit()` itself (same
    pattern as `record_audit_log`): every call site below invokes it
    in the middle of an existing service transaction, so the
    notification is committed atomically together with the state
    change it describes, by that transaction's own commit.
  - `list_notifications_query` — a user's own notifications, newest
    first, with an optional `unread_only` filter
  - `count_unread` — how many of a user's notifications are unread
  - `mark_notification_read` — marks one of the current user's own
    notifications as read; idempotent (marking an already-read
    notification is a no-op, not an error)
- **Wired into existing services** — each of these now also creates a
  notification for the other side of the interaction, as part of the
  same transaction as the state change itself:
  - `request_service.create_request` → notifies the **provider**
    (`request_received`)
  - `request_service.accept_request` → notifies the **recipient**
    (`request_accepted`)
  - `request_service.reject_request` → notifies the **recipient**
    (`request_rejected`)
  - `request_service.cancel_request` → notifies the **provider**
    (`request_cancelled`)
  - `pickup_service.schedule_pickup` → notifies the **recipient**
    (`pickup_scheduled`)
  - `pickup_service.confirm_pickup` → notifies the **provider**
    (`pickup_confirmed`)
  - `pickup_service.complete_pickup` → notifies the **recipient**
    (`pickup_completed`)
  - `pickup_service.fail_pickup` → notifies the **recipient**
    (`pickup_failed`)
  - `pickup_service.cancel_pickup` → notifies the **provider**
    (`pickup_cancelled`)
  - `recipient_service.verify_recipient_profile` → notifies the
    **recipient** (`recipient_verified`)
- `app/routes/notifications.py` (new file):
  - `GET /api/notifications` — my own notifications, paginated,
    newest first. Optional `?unread_only=true` filter. The response
    also includes an `unread_count` alongside the paginated list, so
    a client can show a badge without a second request.
  - `POST /api/notifications/<id>/read` — mark one of my own
    notifications as read (owner only; 403 otherwise)

**No new dependencies or migrations are needed for Phase 9** — the
`notifications` table already existed from Phase 2's initial schema;
this phase only adds the service/route layer on top of it.

### What's included in Phase 10

Phase 10 adds read-only reporting/aggregation on top of the
`DistributionRecord`/`FoodRequest`/`PickupRecord`/`FoodListing` rows
every prior phase has been creating — nothing here writes data, same
"read-only history" spirit as Phase 7's `/api/distributions`
endpoints.

- `app/reports/service.py` (new file, using the `app/reports/`
  folder that's been scaffolded since Phase 2):
  - `distribution_summary` — total distributions, total quantity, and
    unique provider/recipient counts, optionally scoped to one
    provider, one recipient, and/or an inclusive date range (by
    pickup date)
  - `distribution_by_category` — the same scope/filters, broken down
    by `food_category`, ordered by quantity descending
  - `provider_activity_summary` / `recipient_activity_summary` — one
    provider's or recipient's own full activity: listings/requests/
    pickups by status, plus total quantity distributed or received
  - `platform_summary` — admin-only, all-time snapshot: users by
    role, listings by status, recipients by verification status,
    total distributions and quantity
- `app/routes/reports.py` (new file):
  - `GET /api/reports/distributions/summary` — admin, provider, or
    recipient. Optional `start_date`/`end_date` (`YYYY-MM-DD`,
    inclusive). Admins may additionally pass `provider_id`/
    `recipient_id` to narrow the report; providers/recipients are
    always pinned to their own data — those two query params are
    silently ignored for them, not honored, so there's no way to
    view someone else's numbers by passing a different id.
  - `GET /api/reports/distributions/by-category` — same parameters
    and scoping rules as the summary endpoint
  - `GET /api/reports/my-activity` — provider or recipient only: a
    full activity dashboard for the caller's own profile (shape
    differs by role — a provider has no "quantity received" concept
    and vice versa)
  - `GET /api/reports/platform-summary` — admin only: the platform-
    wide snapshot described above

**No new dependencies or migrations are needed for Phase 10** — it's
built entirely on tables and columns that already existed from
earlier phases.

### What's included in Phase 11

Phase 11 is the security review pass promised in Phase 10's preview:
hardening the two unauthenticated endpoints against abuse, and
finally exposing the `AuditLog` table and broader account-management
actions that earlier phases deliberately deferred. No new tables or
migrations — everything here is built on the `AccountStatus` enum
(scaffolded on `User` since Phase 2) and the `AuditLog` rows every
phase has been writing since Phase 3.

- `app/middleware/rate_limit.py` (new file) — a small, dependency-free
  in-memory rate limiter, `@rate_limit(max_requests=, window_seconds=,
  bucket=)`. Applied to the two routes reachable with **no token at
  all**, which makes them the most attractive targets for automated
  abuse:
  - `POST /api/auth/login` — 10 attempts per 5 minutes per caller
    (keyed by IP, not email, so it can't be used to lock a specific
    account out by spamming failed logins from elsewhere)
  - `POST /api/auth/register` — 5 attempts per 5 minutes per caller
  - Exceeding the limit returns `429` with a `Retry-After` header, in
    the project's standard error envelope (`error: "RATE_LIMITED"`).
  - Counters live in this process's memory only — documented as a
    known limitation in the module's own docstring, not hidden. Fine
    for this project's single-process scope; a multi-worker
    deployment would swap this for a shared store (e.g. Redis)
    without changing the decorator's call sites.
- `app/services/auth_service.py` — `authenticate_user` now also
  writes an audit-log entry (`login_failed`) on every unsuccessful
  login: unknown email, wrong password, or a deactivated account —
  three separate `description`s so the audit trail can distinguish
  them, but the client-facing error message stays the same generic
  "Invalid email or password" either way (unchanged from Phase 3),
  so this adds visibility for admins without adding any new way to
  enumerate accounts from the API response itself.
- `app/services/admin_service.py` (new file) — administrator user
  management:
  - `list_users_query` — every user account, filterable by `role`,
    `status`, and a `search` substring match on name/email
  - `get_user_or_404`
  - `deactivate_user` / `activate_user` — flips `User.status`
    between `ACTIVE`/`INACTIVE`. Both are idempotent (repeating the
    action is a success, not an error), both write an audit-log entry
    and notify the affected user, and `deactivate_user` refuses to
    let an admin deactivate their own account (no other admin action
    exists to undo that, so it would be an unrecoverable self-lockout
    short of editing the database directly). No token-blocklist
    bookkeeping is needed here: `token_required` (Phase 3) already
    rejects every request from a non-`ACTIVE` account, so a
    deactivation takes effect on that user's very next request even
    if their current token hasn't expired yet.
- `app/services/audit_service.py` (new file) — `list_audit_logs_query`:
  the audit trail, filterable by `user_id`, `action`, `resource_type`,
  and an inclusive `start_date`/`end_date` range on `timestamp`.
  Read-only, same spirit as Phase 10's reports.
- `app/routes/admin.py` (new file):
  - `GET /api/admin/users` — list/filter every account, paginated
  - `GET /api/admin/users/<id>` — view one account's details
  - `POST /api/admin/users/<id>/deactivate` — suspend an account
  - `POST /api/admin/users/<id>/activate` — reactivate an account
- `app/routes/audit.py` (new file):
  - `GET /api/audit-logs` — the full audit trail, filterable,
    paginated

All five new/changed routes above are **admin-only**
(`@role_required(UserRole.ADMIN)`); the two rate-limited routes stay
public, as they must be to serve their purpose (you can't require a
token to log in).

**No new dependencies or migrations are needed for Phase 11** — the
rate limiter is pure Python, `AccountStatus` has existed on `User`
since Phase 2, and `AuditLog` has existed and been written to since
Phase 3.

### What's included in Phases 1–6 (still active)

- Flask foundation, PostgreSQL schema, authentication, provider
  profiles + listings, recipient profiles + public browsing/search/pagination,
  the request workflow (submit/accept/reject/cancel with
  quantity-safety guarantees)

---

## Folder Structure

```text
foodrescue_network/
│
├── app/
│   ├── __init__.py          # App factory: create_app()
│   ├── config.py            # Environment-based configuration
│   │
│   ├── models/               # (Phase 2) SQLAlchemy database models
│   ├── routes/                # Flask blueprints (API endpoints)
│   │   └── health.py          # GET /api/health
│   ├── services/              # (Phase 4+) business logic
│   ├── schemas/               # (Phase 4+) request/response validation
│   ├── auth/                  # (Phase 3) authentication & authorization
│   ├── notifications/         # (Phase 9) notification logic
│   ├── reports/               # (Phase 10) reporting logic
│   ├── utils/                 # shared helper functions
│   └── middleware/            # (Phase 11) ✅ rate limiting; auth checks live in app/auth/
│
├── uploads/                  # (optional, unused so far) uploaded files
├── tests/                    # (Phase 12) automated tests
│
├── .env                      # your real secrets (NEVER commit this)
├── .env.example              # placeholder values, safe to commit
├── .gitignore
├── requirements.txt
├── run.py                    # local dev entry point
└── README.md
```

---

## 1. Prerequisites

- Python 3.10+
- PostgreSQL 13+ installed and running (only needed starting Phase 2,
  but it's worth installing now)
- `pip` / a virtual environment tool

---

## 2. Setup

```bash
# 1. Clone / enter the project folder
cd foodrescue_network

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create your local .env file from the example
cp .env.example .env
```

Open `.env` and fill in real values:

```text
FLASK_ENV=development
SECRET_KEY=<generate one — see below>
DATABASE_URL=postgresql://foodrescue_user:yourpassword@localhost:5432/foodrescue_db
```

Generate a secure `SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

> **PostgreSQL note:** Phase 1 does not yet connect to the database
> (that begins in Phase 2), so `DATABASE_URL` can be left as a
> placeholder for now — but it's good practice to set up the real
> value early.

---

## 3. Running the API

```bash
python run.py
```

You should see Flask start up and log something like:

```text
* Running on http://0.0.0.0:5000
```

---

## 4. Testing Phase 1 with Postman (or curl)

### Health Check

**Request**

```text
GET http://localhost:5000/api/health
```

No authentication required.

**Expected response — 200 OK**

```json
{
    "success": true,
    "message": "FoodRescue Network API is running",
    "data": {
        "service": "foodrescue-network-api",
        "status": "healthy"
    }
}
```

**Using curl instead of Postman:**

```bash
curl http://localhost:5000/api/health
```

### Testing error handling

Try an endpoint that doesn't exist:

```text
GET http://localhost:5000/api/does-not-exist
```

**Expected response — 404 Not Found**

```json
{
    "success": false,
    "message": "The requested resource was not found.",
    "error": "NOT_FOUND"
}
```

This confirms the centralized error handler (in `app/__init__.py`)
is working and that we never expose raw Flask/Werkzeug HTML error
pages or stack traces to API clients.

---

## 5. Phase 2: Setting Up PostgreSQL

### 5.1 Install PostgreSQL

If you haven't already, install PostgreSQL 13+ and make sure the
`psql` command-line tool and the PostgreSQL service are available.

### 5.2 Create the database and a dedicated user

Open `psql` (or any PostgreSQL client) as an admin/superuser and run:

```sql
CREATE USER foodrescue_user WITH PASSWORD 'yourpassword';
CREATE DATABASE foodrescue_db OWNER foodrescue_user;
GRANT ALL PRIVILEGES ON DATABASE foodrescue_db TO foodrescue_user;
```

> Use a real password of your choice — just make sure it matches
> what you put in `.env` next.

### 5.3 Point `.env` at your real database

Open `.env` and update `DATABASE_URL` to match what you just created:

```text
DATABASE_URL=postgresql://foodrescue_user:yourpassword@localhost:5432/foodrescue_db
```

### 5.4 Install the new dependencies

```bash
pip install -r requirements.txt
```

This installs `Flask-SQLAlchemy`, `Flask-Migrate`, and `psycopg2-binary`
(the PostgreSQL driver) in addition to what Phase 1 installed.

### 5.5 Initialize migrations and create the tables

Flask-Migrate uses Alembic under the hood to track schema changes as
versioned Python files — this is what lets a team evolve the database
safely over the life of a long-term project, instead of manually
running `CREATE TABLE` statements.

```bash
# Only run this once, ever, for the whole project:
flask --app run.py db init

# Generate a migration by comparing the models to the current DB schema:
flask --app run.py db migrate -m "Initial schema: users, profiles, listings, requests, pickups, distributions, notifications, audit logs"

# Apply the migration — this actually creates the tables in PostgreSQL:
flask --app run.py db upgrade
```

After this, connect with `psql` and run `\dt` — you should see all
nine tables listed (`users`, `provider_profiles`, `recipient_profiles`,
`food_listings`, `food_requests`, `pickup_records`,
`distribution_records`, `notifications`, `audit_logs`), plus Alembic's
own `alembic_version` bookkeeping table.

### 5.6 Verify with the health-check endpoint

Start the server (`python run.py`) and visit:

```text
GET http://localhost:5000/api/health
```

**Expected response — 200 OK**

```json
{
    "success": true,
    "message": "FoodRescue Network API is running",
    "data": {
        "service": "foodrescue-network-api",
        "status": "healthy",
        "database": "healthy"
    }
}
```

If `DATABASE_URL` is wrong or PostgreSQL isn't running, you'll instead
see `"database": "unreachable"` with a `503` status — that's the
health check doing its job.

---

## 6. Phase 3: Testing Authentication

### 6.1 Install the new dependencies

```bash
pip install -r requirements.txt
```

This installs `PyJWT` (tokens) and `bcrypt` (password hashing) on top
of everything from Phase 1/2.

### 6.2 Apply the new migration

Phase 3 adds one new table (`token_blocklist`, for logout support),
so we need a new migration:

```bash
flask --app run.py db migrate -m "Add token blocklist for logout"
flask --app run.py db upgrade
```

### 6.3 Register a Provider account

**Request**

```text
POST http://localhost:5000/api/auth/register
Content-Type: application/json

{
    "name": "Green Table Restaurant",
    "email": "contact@greentable.example",
    "password": "SecurePass123",
    "role": "provider"
}
```

**Expected response — 201 Created**

```json
{
    "success": true,
    "message": "Account registered successfully.",
    "data": {
        "id": 1,
        "name": "Green Table Restaurant",
        "email": "contact@greentable.example",
        "role": "provider",
        "status": "active",
        "created_at": "...",
        "updated_at": "..."
    }
}
```

Notice there is no `password_hash` field anywhere in the response.

Try registering the same email again — you should get:

```json
{
    "success": false,
    "message": "An account with this email already exists.",
    "error": "EMAIL_ALREADY_REGISTERED"
}
```
(status 409)

Try registering with `"role": "admin"` — you should get a validation
error (422). Public registration cannot create administrators.

### 6.4 Log in

**Request**

```text
POST http://localhost:5000/api/auth/login
Content-Type: application/json

{
    "email": "contact@greentable.example",
    "password": "SecurePass123"
}
```

**Expected response — 200 OK**

```json
{
    "success": true,
    "message": "Login successful.",
    "data": {
        "token": "eyJhbGciOiJIUzI1NiIs...",
        "user": { "...": "..." }
    }
}
```

Copy the `token` value — you'll need it for the next requests.

### 6.5 Access a protected endpoint

**Request**

```text
GET http://localhost:5000/api/profile
Authorization: Bearer <paste your token here>
```

**Expected response — 200 OK** — your own account info.

Now try the same request **without** the `Authorization` header —
you should get:

```json
{
    "success": false,
    "message": "Authentication required. Provide a Bearer token.",
    "error": "AUTH_HEADER_MISSING"
}
```
(status 401)

### 6.6 Log out

**Request**

```text
POST http://localhost:5000/api/auth/logout
Authorization: Bearer <your token>
```

**Expected response — 200 OK** — `"Logged out successfully."`

Now try `GET /api/profile` again with that **same** token — it
should now be rejected with `"error": "TOKEN_REVOKED"`, even though
the token hasn't expired. That confirms logout actually works.

---

## 8. Phase 4: Testing the Provider Module

No new dependencies or migrations are needed for Phase 4 — it only
adds routes and business logic on top of tables that already exist.

### 8.1 Create your provider profile

Using the same provider account and token from Phase 3:

**Request**

```text
POST http://localhost:5000/api/providers/profile
Authorization: Bearer <your token>
Content-Type: application/json

{
    "organization_name": "Green Table Restaurant",
    "contact_info": "+1 555-0100",
    "address": "12 Market St",
    "city": "Springfield",
    "latitude": 39.799999,
    "longitude": -89.644444,
    "description": "Family-owned Italian restaurant."
}
```

**Expected response — 201 Created** with your new profile.

Try sending the exact same request again — you should get:
```json
{"success": false, "message": "A provider profile already exists for this account. Use update instead.", "error": "PROFILE_ALREADY_EXISTS"}
```
(status 409)

### 8.2 Create a food listing

**Request**

```text
POST http://localhost:5000/api/listings
Authorization: Bearer <your token>
Content-Type: application/json

{
    "food_name": "Vegetable Biryani",
    "description": "Freshly cooked, from tonight's event.",
    "category": "prepared_food",
    "quantity": 50,
    "quantity_unit": "meals",
    "available_date": "2026-09-10",
    "pickup_start_time": "2026-09-10T17:00:00+00:00",
    "pickup_end_time": "2026-09-10T19:00:00+00:00",
    "pickup_location": "12 Market St, Springfield",
    "latitude": 39.799999,
    "longitude": -89.644444,
    "conditions": "Pickup only. Keep refrigerated."
}
```

**Expected response — 201 Created** with `"status": "available"`.

Try these to confirm validation works:
- Set `"quantity": -5` → expect a 422 `VALIDATION_ERROR`
- Set `"pickup_end_time"` earlier than `"pickup_start_time"` → expect a 422
- Set `"category": "not_real"` → expect a 422

### 8.3 View your listings

```text
GET http://localhost:5000/api/listings/mine
Authorization: Bearer <your token>
```

You should see the listing you just created.

### 8.4 Test ownership protection

Register a **second** provider account, log in as them, complete
their profile, then try to update or cancel the **first** provider's
listing using the second provider's token:

```text
PUT http://localhost:5000/api/listings/1
Authorization: Bearer <second provider's token>
Content-Type: application/json

{"food_name": "Hacked!"}
```

**Expected response — 403 Forbidden**
```json
{"success": false, "message": "You do not have permission to modify this listing.", "error": "FORBIDDEN"}
```

### 8.5 Cancel a listing

```text
POST http://localhost:5000/api/listings/1/cancel
Authorization: Bearer <the OWNING provider's token>
```

**Expected response — 200 OK** with `"status": "cancelled"`.

Try cancelling it again — you should get a 409 `INVALID_LISTING_STATE`,
since it's no longer `available`.

---

## 11. Phase 5: Testing the Recipient Module

No new dependencies or migrations are needed for Phase 5 either — it
only adds routes and business logic on top of tables that already
exist.

### 11.1 Register and set up a Recipient account

**Request**
```text
POST http://localhost:5000/api/auth/register
Content-Type: application/json

{
    "name": "Hope Community Shelter",
    "email": "contact@hopeshelter.example",
    "password": "SecurePass123",
    "role": "recipient"
}
```

Then log in the same way as before to get a token, and create their profile:

```text
POST http://localhost:5000/api/recipients/profile
Authorization: Bearer <recipient's token>
Content-Type: application/json

{
    "organization_name": "Hope Community Shelter",
    "contact_info": "+1 555-0200",
    "address": "88 Elm St",
    "city": "Springfield",
    "latitude": 39.801,
    "longitude": -89.650,
    "description": "Shelter serving 60 residents nightly."
}
```

**Expected response — 201 Created**, with `"verification_status": "pending"`.

### 11.2 Browse available listings

Using **any** logged-in user's token (recipient, provider, or admin):

```text
GET http://localhost:5000/api/listings
Authorization: Bearer <any token>
```

**Expected response — 200 OK**
```json
{
    "success": true,
    "message": "Listings retrieved successfully.",
    "data": {
        "listings": [ { "...": "the biryani listing from Phase 4" } ],
        "pagination": {"page": 1, "limit": 10, "total": 1, "total_pages": 1}
    }
}
```

If you cancelled that listing while testing Phase 4, create a fresh
one first (`POST /api/listings` as the provider) so there's something
to browse.

### 11.3 Test filtering

```text
GET http://localhost:5000/api/listings?category=prepared_food
GET http://localhost:5000/api/listings?city=springfield
GET http://localhost:5000/api/listings?category=bakery
```

The last one should return an empty `listings` array (no bakery items
exist yet) but still `"success": true` with correct pagination
metadata (`"total": 0`).

Try an invalid category:
```text
GET http://localhost:5000/api/listings?category=not_real
```
**Expected — 422** `VALIDATION_ERROR`.

### 11.4 Test pagination

```text
GET http://localhost:5000/api/listings?page=1&limit=1
```

Check the `pagination` object matches what you'd expect given how
many listings exist.

---

## 14. Phase 6: Testing the Request Workflow

No new dependencies or migrations are needed for Phase 6.

### 14.1 Bootstrap your first administrator account (one-time, manual)

There is no public "become an admin" endpoint (by design — spec
section 5). For testing, we'll promote an existing account directly
in the database using pgAdmin.

**Step 1:** Register a normal account to promote (or reuse one you
already have) — for example, register with:
```json
{"name": "Admin Test", "email": "admin@example.com", "password": "SecurePass123", "role": "recipient"}
```
(The role you register with doesn't matter — we're about to overwrite it.)

**Step 2:** In pgAdmin, open a Query Tool on `foodrescue_db` and run:
```sql
UPDATE users SET role = 'admin' WHERE email = 'admin@example.com';
```

**Step 3:** Log in as that account normally (`POST /api/auth/login`) —
the token you get back will now have `"role": "admin"` embedded in it.

### 14.2 Verify your recipient

Using the **admin** token from above:

```text
POST http://localhost:5000/api/recipients/1/verify
Authorization: Bearer <admin token>
```

(Use whatever recipient profile ID your Phase 5 "Hope Community
Shelter" profile actually has — check with `GET /api/recipients/profile`
using the recipient's own token if unsure.)

**Expected response — 200 OK** with `"verification_status": "verified"`.

### 14.3 Submit a food request

Using the **recipient's own** token:

```text
POST http://localhost:5000/api/requests
Authorization: Bearer <recipient token>
Content-Type: application/json

{
    "listing_id": 1,
    "requested_quantity": 20,
    "request_message": "We can pick up any time after 5pm."
}
```

**Expected response — 201 Created** with `"status": "pending"`.

Try submitting a **second** request for the same listing from the
same recipient — expect a 409 `DUPLICATE_REQUEST`.

Try requesting more than the listing has (e.g. `"requested_quantity": 999`)
— expect a 409 `QUANTITY_EXCEEDS_AVAILABLE`.

### 14.4 Provider accepts the request

Using the **provider's** token:

```text
GET http://localhost:5000/api/listings/1/requests
Authorization: Bearer <provider token>
```

You should see the pending request. Now accept it:

```text
POST http://localhost:5000/api/requests/1/accept
Authorization: Bearer <provider token>
```

**Expected response — 200 OK** with `"status": "accepted"`.

Try accepting it again — expect a 409 `INVALID_REQUEST_STATE`
(it's no longer pending).

### 14.5 Confirm the quantity math

If your listing had 50 meals and this request was for 20, there
should be 30 remaining. Register a **third** recipient, get them
verified (repeat 14.1–14.2), and try requesting **40** from the same
listing — that should succeed (40 ≤ 30 is false... wait, it should
actually be **rejected**, since only 30 remain). Try requesting
**25** instead — that should succeed, since 25 ≤ 30.

### 14.6 Test rejection and cancellation

Create one more request, then reject it as the provider:
```text
POST http://localhost:5000/api/requests/<id>/reject
Authorization: Bearer <provider token>
```
**Expected — 200 OK** with `"status": "rejected"`.

As a recipient, cancel one of your own pending/accepted requests:
```text
POST http://localhost:5000/api/requests/<id>/cancel
Authorization: Bearer <recipient token>
```
**Expected — 200 OK** with `"status": "cancelled"` — and if it had
been accepted, the freed-up quantity should now allow a new request
of that size again.

---

## 15. Phase 7: Testing Pickup and Distribution

No new dependencies or migrations are needed for Phase 7.

Pick up right where the Phase 6 walkthrough left off — you should
have an **accepted** request (section 14.4) between a provider and a
verified recipient.

### 15a.1 Provider schedules the pickup

Using the **provider's** token:

```text
POST http://localhost:5000/api/requests/1/schedule-pickup
Authorization: Bearer <provider token>
Content-Type: application/json

{
    "pickup_time": "2026-09-10T18:00:00+00:00",
    "confirmation_info": "Use the back entrance on Market St."
}
```

**Expected response — 201 Created** with `"status": "scheduled"`.

Try scheduling a second pickup for the same request — expect a 409
`PICKUP_ALREADY_SCHEDULED`.

Try scheduling a pickup for a request that's still `pending` (not
yet accepted) — expect a 409 `INVALID_REQUEST_STATE`.

### 15a.2 Recipient confirms

Using the **recipient's** token:

```text
POST http://localhost:5000/api/pickups/1/confirm
Authorization: Bearer <recipient token>
```

**Expected response — 200 OK** with `"status": "confirmed"`.

Try confirming it again — expect a 409 `INVALID_PICKUP_STATE`.

### 15a.3 Provider completes the pickup

```text
POST http://localhost:5000/api/pickups/1/complete
Authorization: Bearer <provider token>
Content-Type: application/json

{"confirmation_info": "Picked up by shelter volunteer, signed for."}
```

**Expected response — 200 OK** with `"status": "completed"` and a
`pickup_time` filled in (defaults to "now" if you don't pass one).

Check that it actually happened:

```text
GET http://localhost:5000/api/requests/1
Authorization: Bearer <provider token>
```

`"status"` should now be `"completed"`.

```text
GET http://localhost:5000/api/distributions
Authorization: Bearer <provider token>
```

You should see one distribution record for this pickup — this is
the permanent history entry.

If this was the **only** accepted request against that listing,
check the listing too:

```text
GET http://localhost:5000/api/listings/1
Authorization: Bearer <any token>
```

`"status"` should now be `"collected"`.

Try completing the same pickup again — expect a 409
`INVALID_PICKUP_STATE`.

### 15a.4 Test the failure/cancel paths

Create and accept a fresh request (repeat 14.3–14.4), then schedule
its pickup. As the **provider**, mark it failed:

```text
POST http://localhost:5000/api/pickups/<new pickup id>/fail
Authorization: Bearer <provider token>
Content-Type: application/json

{"reason": "Recipient did not show up."}
```

**Expected response — 200 OK** with `"status": "failed"`. Check the
request — it should have reverted to `"accepted"`, so you can
schedule a new pickup for it.

Alternatively, as the **recipient**, cancel a scheduled pickup:

```text
POST http://localhost:5000/api/pickups/<pickup id>/cancel
Authorization: Bearer <recipient token>
```

**Expected response — 200 OK** with `"status": "cancelled"`, and the
request reverted to `"accepted"` again.

### 15a.5 Test permission boundaries

Try confirming/completing a pickup using a **different** provider or
recipient's token — expect a 403 `FORBIDDEN` in every case.

---

## 15b. Phase 8: Testing Location-Based Search

No new dependencies or migrations are needed for Phase 8. Pick up
right where the Phase 7 walkthrough left off — you should have at
least one provider profile and one recipient profile with
coordinates on file (sections 8.1 and 11.1), plus a couple of
`available` listings.

### 15b.1 Browse listings near an explicit point

Using **any** logged-in user's token:

```text
GET http://localhost:5000/api/listings?near_lat=39.80&near_lng=-89.64&radius_km=10
Authorization: Bearer <any token>
```

**Expected response — 200 OK** — same shape as plain `GET
/api/listings`, except every listing now has a `distance_km` field
and the list is ordered nearest-first instead of newest-first.

Try a very small radius that should exclude everything:
```text
GET http://localhost:5000/api/listings?near_lat=0&near_lng=0&radius_km=1
```
**Expected** — `"listings": []` with `"total": 0` (Springfield's test
coordinates are nowhere near 0,0).

Try supplying only `near_lat` without `near_lng`:
```text
GET http://localhost:5000/api/listings?near_lat=39.80
```
**Expected — 422** `VALIDATION_ERROR` — `"Both near_lat and near_lng
must be provided together."`

### 15b.2 Browse listings near MY OWN profile

Using the **recipient's** token (their profile needs coordinates —
section 11.1 already set some):

```text
GET http://localhost:5000/api/listings?near_me=true&radius_km=10
Authorization: Bearer <recipient token>
```

**Expected — 200 OK** with `distance_km` on each listing, computed
from the recipient's own profile coordinates.

If you try this with an account that has **no** provider or
recipient profile yet, expect:
```json
{"success": false, "message": "near_me requires a profile with latitude/longitude on file.", "error": "VALIDATION_ERROR"}
```
(status 422)

### 15b.3 Provider: find nearby verified recipients

Using the **provider's** token:

```text
GET http://localhost:5000/api/providers/nearby-recipients?radius_km=20
Authorization: Bearer <provider token>
```

**Expected — 200 OK**
```json
{
    "success": true,
    "message": "Nearby verified recipients retrieved successfully.",
    "data": {
        "recipients": [ {"...": "...", "distance_km": 0.31} ],
        "pagination": {"page": 1, "limit": 10, "total": 1, "total_pages": 1}
    }
}
```

Only **verified** recipients show up — if you haven't verified any
recipient yet (section 14.2), this will come back empty even if
unverified recipients exist nearby.

### 15b.4 Recipient: find nearby providers with availability

Using the **recipient's** token:

```text
GET http://localhost:5000/api/recipients/nearby-providers?radius_km=20
Authorization: Bearer <recipient token>
```

**Expected — 200 OK** — providers within range who currently have at
least one `available` listing, nearest first. If every listing from a
nearby provider has already moved past `available` (e.g. `collected`,
per Phase 7 testing), that provider won't appear here even though
they're geographically close — this endpoint is about who has food
*right now*, not who exists nearby.

### 15b.5 Test radius validation

```text
GET http://localhost:5000/api/listings?near_lat=39.80&near_lng=-89.64&radius_km=-5
```
**Expected — 422** — `"radius_km must be greater than zero."`

```text
GET http://localhost:5000/api/listings?near_lat=39.80&near_lng=-89.64&radius_km=9999
```
**Expected — 422** — `"radius_km must be 500 or less."`

---

## 15c. Phase 9: Testing Notifications

No new dependencies or migrations are needed for Phase 9. Pick up
right where the Phase 8 walkthrough left off, or replay a few events
from Phases 6-7 (submit a request, accept it, schedule a pickup) —
each one now leaves a notification behind for the other party.

### 15c.1 Trigger a notification

Using the **recipient's** token, submit a request (section 14.3) if
you don't already have one pending. Then, using the **provider's**
token:

```text
GET http://localhost:5000/api/notifications
Authorization: Bearer <provider token>
```

**Expected response — 200 OK**

```json
{
    "success": true,
    "message": "Notifications retrieved successfully.",
    "data": {
        "notifications": [
            {
                "id": 1,
                "user_id": 1,
                "notification_type": "request_received",
                "title": "New request for your listing",
                "message": "A recipient requested 20 meals of 'Vegetable Biryani'.",
                "related_resource_type": "food_request",
                "related_resource_id": 1,
                "is_read": false,
                "created_at": "..."
            }
        ],
        "pagination": {"page": 1, "limit": 10, "total": 1, "total_pages": 1},
        "unread_count": 1
    }
}
```

### 15c.2 Filter to unread only

```text
GET http://localhost:5000/api/notifications?unread_only=true
Authorization: Bearer <provider token>
```

Should return the same notification. Now mark it read:

```text
POST http://localhost:5000/api/notifications/1/read
Authorization: Bearer <provider token>
```

**Expected response — 200 OK** with `"is_read": true`. Repeat the
`unread_only=true` request — the list should now come back empty and
`unread_count` should have dropped by one.

Try marking it read a second time — still **200 OK** (marking an
already-read notification is a no-op, not an error).

### 15c.3 Test the accept/reject/pickup notifications

Using the **provider's** token, accept the request (section 14.4).
Then, using the **recipient's** token:

```text
GET http://localhost:5000/api/notifications
Authorization: Bearer <recipient token>
```

You should see a `request_accepted` notification. Continue through
the pickup lifecycle (sections 15a.1-15a.3) and check each side's
notifications along the way — `pickup_scheduled` lands on the
recipient, `pickup_confirmed` lands on the provider, and
`pickup_completed` lands on the recipient again.

### 15c.4 Test ownership protection

Try marking a notification read using a token that doesn't own it:

```text
POST http://localhost:5000/api/notifications/1/read
Authorization: Bearer <a different user's token>
```

**Expected response — 403 Forbidden**
```json
{"success": false, "message": "You do not have permission to view this notification.", "error": "FORBIDDEN"}
```

Try an ID that doesn't exist:

```text
POST http://localhost:5000/api/notifications/99999/read
Authorization: Bearer <any token>
```

**Expected — 404** `NOTIFICATION_NOT_FOUND`.

---

## 15d. Phase 10: Testing Reports

No new dependencies or migrations are needed for Phase 10. Pick up
with the provider/recipient/admin tokens and the completed
distribution(s) from earlier phases (section 15.5 onward).

### 15d.1 Provider's own distribution summary

```text
GET http://localhost:5000/api/reports/distributions/summary
Authorization: Bearer <provider token>
```

**Expected — 200 OK**
```json
{
    "success": true,
    "message": "Distribution summary retrieved successfully.",
    "data": {
        "total_distributions": 1,
        "total_quantity": 20.0,
        "unique_providers": 1,
        "unique_recipients": 1,
        "filters": {"provider_id": 3, "recipient_id": null, "start_date": null, "end_date": null}
    }
}
```

The `provider_id` in `filters` is filled in automatically from your
own profile — you never pass it yourself as a provider.

### 15d.2 Breakdown by category

```text
GET http://localhost:5000/api/reports/distributions/by-category
Authorization: Bearer <provider token>
```

**Expected — 200 OK** — a `categories` array, one entry per
`food_category` you've distributed, each with `distributions` (count)
and `total_quantity`, sorted highest-quantity first.

### 15d.3 Date-range filtering

```text
GET http://localhost:5000/api/reports/distributions/summary?start_date=2026-09-01&end_date=2026-09-30
Authorization: Bearer <provider token>
```

**Expected — 200 OK** with the same shape, scoped to that window. Try
a range that couldn't contain any of your test data (e.g.
`start_date=2020-01-01&end_date=2020-01-31`) — expect
`"total_distributions": 0`.

Try an invalid range (start after end):
```text
GET http://localhost:5000/api/reports/distributions/summary?start_date=2026-09-30&end_date=2026-09-01
```
**Expected — 422** — `"start_date must not be after end_date."`

### 15d.4 My activity dashboard

```text
GET http://localhost:5000/api/reports/my-activity
Authorization: Bearer <provider token>
```

**Expected — 200 OK**
```json
{
    "data": {
        "listings_by_status": {"available": 1, "collected": 1},
        "requests_by_status": {"pending": 0, "accepted": 1, ...},
        "pickups_by_status": {"completed": 1, "failed": 1, "cancelled": 1},
        "total_quantity_distributed": 20.0
    }
}
```

Repeat with the **recipient's** token — expect
`"total_quantity_received"` instead of `"total_quantity_distributed"`,
and no `listings_by_status` (recipients don't own listings).

### 15d.5 Admin: platform-wide summary

```text
GET http://localhost:5000/api/reports/platform-summary
Authorization: Bearer <admin token>
```

**Expected — 200 OK** — `users_by_role`, `listings_by_status`,
`recipients_by_verification`, `total_distributions`,
`total_quantity_distributed`, covering every account and record on
the platform (not date-scoped).

Try it with a non-admin token — expect **403 FORBIDDEN**.

### 15d.6 Admin: drill into one provider or recipient

```text
GET http://localhost:5000/api/reports/distributions/summary?provider_id=3
Authorization: Bearer <admin token>
```

**Expected — 200 OK** scoped to just that provider's numbers. Try the
same URL with the **provider's own** token instead — the `provider_id`
query param is silently ignored and it still only ever sees its own
data (you can confirm this by trying `?provider_id=<some other id>`
and seeing the response doesn't change).

### 15d.7 Role restriction on my-activity

```text
GET http://localhost:5000/api/reports/my-activity
Authorization: Bearer <admin token>
```

**Expected — 403 FORBIDDEN** — `/my-activity` only makes sense for a
provider or recipient's own profile; admins use `/platform-summary`
and the scoped `/distributions/*` reports instead.

## 15e. Phase 11: Testing Security and Audit

No new dependencies or migrations are needed for Phase 11. Pick up
with the admin token from earlier phases (section 14.1).

### 15e.1 Trigger the login rate limit

```text
POST http://localhost:5000/api/auth/login
Content-Type: application/json

{"email": "nobody@example.com", "password": "wrong-password"}
```

Send this **11 times in a row** within 5 minutes.

**Expected — the first 10 return `401` `INVALID_CREDENTIALS`; the
11th returns:**
```json
{
    "success": false,
    "message": "Too many requests. Please wait before trying again.",
    "error": "RATE_LIMITED"
}
```
with a `429` status and a `Retry-After` header. Check
`GET /api/audit-logs?action=login_failed` (admin token) afterward —
you should see one entry per attempt that actually reached the
service (i.e. the 10 that weren't rate-limited).

### 15e.2 Trigger the registration rate limit

Same idea, `POST /api/auth/register` with any body, 6 times within 5
minutes — the 6th returns `429`.

### 15e.3 Admin: list and filter users

```text
GET http://localhost:5000/api/admin/users?role=recipient&status=active
Authorization: Bearer <admin token>
```

**Expected — 200 OK** — a paginated `users` array. Try
`?search=green` to match on name/email substrings. Try any of this
with a non-admin token — expect **403 FORBIDDEN**.

### 15e.4 Admin: deactivate and reactivate an account

```text
POST http://localhost:5000/api/admin/users/<recipient_user_id>/deactivate
Authorization: Bearer <admin token>
```

**Expected — 200 OK**, `"status": "inactive"` in the returned user.
Now try logging in as that user, or using their existing (still
unexpired) token on any protected endpoint:

**Expected — 401/403** — `ACCOUNT_INACTIVE`, immediately, even though
the token itself hasn't expired.

Reactivate it:
```text
POST http://localhost:5000/api/admin/users/<recipient_user_id>/activate
Authorization: Bearer <admin token>
```
**Expected — 200 OK**, `"status": "active"` again, and the same old
token works once more.

Repeat the deactivate call a second time in a row — **expected 200
OK**, unchanged (idempotent), not an error.

Try deactivating your own admin account:
```text
POST http://localhost:5000/api/admin/users/<your_own_admin_id>/deactivate
Authorization: Bearer <admin token>
```
**Expected — 400** — `CANNOT_DEACTIVATE_SELF`.

### 15e.5 Admin: browse the audit trail

```text
GET http://localhost:5000/api/audit-logs?action=account_deactivated
Authorization: Bearer <admin token>
```

**Expected — 200 OK** — a paginated `audit_logs` array containing the
deactivation from 15e.4, with your admin `user_id` as the actor.
Try `?start_date=&end_date=` and `?resource_type=user` filters too.
Try this endpoint with a non-admin token — expect **403 FORBIDDEN**.

---

## 16. Endpoint reference — Phase 7

| Method | Endpoint | Who | Notes |
|---|---|---|---|
| POST | `/api/requests/<id>/schedule-pickup` | Provider (owner) | request must be `accepted` |
| GET | `/api/pickups` | Provider or Recipient | my pickups, paginated |
| GET | `/api/pickups/<id>` | Owning provider or recipient | |
| POST | `/api/pickups/<id>/confirm` | Recipient (owner) | pickup must be `scheduled` |
| POST | `/api/pickups/<id>/complete` | Provider (owner) | pickup must be `scheduled`/`confirmed`; creates the `DistributionRecord` |
| POST | `/api/pickups/<id>/fail` | Provider (owner) | pickup must be `scheduled`/`confirmed`; request reverts to `accepted` |
| POST | `/api/pickups/<id>/cancel` | Recipient (owner) | pickup must be `scheduled`/`confirmed`; request reverts to `accepted` |
| GET | `/api/distributions` | Provider or Recipient | my distribution history, paginated |
| GET | `/api/distributions/<id>` | Owning provider or recipient | read-only, permanent record |

## 16b. Endpoint reference — Phase 8

| Method | Endpoint | Who | Notes |
|---|---|---|---|
| GET | `/api/listings?near_lat=&near_lng=&radius_km=` | Any logged-in user | adds `distance_km`, sorts nearest-first |
| GET | `/api/listings?near_me=true&radius_km=` | Any logged-in user with a profile | uses caller's own profile coordinates |
| GET | `/api/providers/nearby-recipients?radius_km=` | Provider | nearest **verified** recipients to my profile |
| GET | `/api/recipients/nearby-providers?radius_km=` | Recipient | nearest providers with an **available** listing |

## 16c. Endpoint reference — Phase 9

| Method | Endpoint | Who | Notes |
|---|---|---|---|
| GET | `/api/notifications` | Any logged-in user | my notifications, paginated, newest first; `?unread_only=true` to filter |
| POST | `/api/notifications/<id>/read` | Owner only | idempotent — already-read is not an error |

## 16d. Endpoint reference — Phase 10

| Method | Endpoint | Who | Notes |
|---|---|---|---|
| GET | `/api/reports/distributions/summary` | Admin, Provider, or Recipient | own data only for provider/recipient; `?start_date=&end_date=` optional; admin may add `?provider_id=&recipient_id=` |
| GET | `/api/reports/distributions/by-category` | Admin, Provider, or Recipient | same parameters/scoping as summary |
| GET | `/api/reports/my-activity` | Provider or Recipient | own full activity dashboard; 403 for admin |
| GET | `/api/reports/platform-summary` | Admin only | all-time, platform-wide, not date-scoped |

## 16e. Endpoint reference — Phase 11

| Method | Endpoint | Who | Notes |
|---|---|---|---|
| POST | `/api/auth/login` | Public | rate-limited: 10 attempts / 5 min per caller |
| POST | `/api/auth/register` | Public | rate-limited: 5 attempts / 5 min per caller |
| GET | `/api/admin/users` | Admin only | filter by `role`, `status`, `search`; paginated |
| GET | `/api/admin/users/<id>` | Admin only | one account's details |
| POST | `/api/admin/users/<id>/deactivate` | Admin only | idempotent; 400 if targeting your own account |
| POST | `/api/admin/users/<id>/activate` | Admin only | idempotent |
| GET | `/api/audit-logs` | Admin only | filter by `user_id`, `action`, `resource_type`, `start_date`/`end_date`; paginated |

---

## 17. Common Errors & Solutions — Phase 7

| Problem | Likely Cause | Fix |
|---|---|---|
| `{"error": "INVALID_REQUEST_STATE"}` on `schedule-pickup` | The request isn't `accepted` yet (still `pending`, or already `pickup_pending`/`completed`) | Accept the request first (section 14.4); check its current status with `GET /api/requests/<id>` |
| `{"error": "PICKUP_ALREADY_SCHEDULED"}` | An active (`scheduled`/`confirmed`) pickup already exists for this request | Complete, fail, or cancel the existing pickup before scheduling a new one |
| `{"error": "INVALID_PICKUP_STATE"}` | You're confirming/completing/failing/cancelling a pickup that's already `completed`, `failed`, or `cancelled` | Check `GET /api/pickups/<id>` for its current status; terminal states can't be moved |
| `{"error": "PICKUP_NOT_FOUND"}` | Wrong pickup ID, or it belongs to a different provider/recipient pair | Double-check the ID from the `schedule-pickup` response |
| Listing still shows `"reserved"` after completing a pickup | Another accepted (or pickup-pending) request against the same listing hasn't been picked up yet | That's expected — the listing only becomes `collected` once every claim is picked up |
| `GET /api/distributions` returns an empty list after completing a pickup | You're checking with the wrong account's token | Distribution history is scoped to the logged-in user's own provider/recipient profile |

---

## 18. Common Errors & Solutions (Phases 1-6)

| Problem | Likely Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'flask'` | Dependencies not installed, or virtualenv not activated | Run `pip install -r requirements.txt` inside an activated venv |
| `RuntimeError` / app fails to start referencing `SECRET_KEY` | `.env` file missing or `SECRET_KEY` not set | Copy `.env.example` to `.env` and fill in a real value |
| Port already in use | Another process is using port 5000 | Set `PORT=5001` (or another free port) in `.env`, or stop the other process |
| `curl: (7) Failed to connect` | Server isn't running, or wrong port | Confirm `python run.py` is running and check the printed port |
| `psycopg2.OperationalError: could not connect to server` | PostgreSQL isn't running, or wrong host/port in `DATABASE_URL` | Make sure the PostgreSQL service is started; double-check `DATABASE_URL` |
| `FATAL: password authentication failed for user` | Wrong username/password in `DATABASE_URL` | Re-check the password you set with `CREATE USER ... WITH PASSWORD ...` |
| `relation "users" does not exist` | Migrations haven't been applied yet | Run `flask --app run.py db upgrade` |
| `Error: Directory migrations already exists` | You ran `flask db init` more than once | Safe to ignore — it only needs to run once ever |
| `permission denied for schema public` | Your PostgreSQL role doesn't have rights to create tables | In pgAdmin's Query Tool, run `GRANT ALL ON SCHEMA public TO <your_db_user>;` |
| `{"error": "AUTH_HEADER_MISSING"}` | You forgot the `Authorization: Bearer <token>` header | Add the header in Postman under the "Authorization" tab (type: Bearer Token) |
| `{"error": "TOKEN_INVALID"}` | Token expired (24h), or you copied it wrong | Log in again to get a fresh token |
| `{"error": "TOKEN_REVOKED"}` | You're reusing a token after logging out with it | Log in again to get a new token |
| `ModuleNotFoundError: No module named 'bcrypt'` or `'jwt'` | New dependencies not installed | Run `pip install -r requirements.txt` again |
| `{"error": "PROFILE_NOT_FOUND"}` when creating a listing | You haven't created your provider profile yet | `POST /api/providers/profile` first |
| `{"error": "FORBIDDEN"}` on a listing you're sure is yours | You're logged in as a different provider account | Double check which account's token you're using |
| `{"error": "INVALID_LISTING_STATE"}` | The listing is no longer `available` (already cancelled/reserved/etc.) | Create a new listing to test further edits |
| Recipient can't see their own listing requests yet | Request workflow is a later phase | That's expected — it's built in Phase 6 |
| `GET /api/listings` returns an empty list unexpectedly | The listing's `pickup_end_time` has already passed, or its status isn't `available` | Create a fresh listing with a future pickup window |
| `{"error": "RECIPIENT_NOT_VERIFIED"}` | The recipient hasn't been verified by an admin yet | Follow section 14.1–14.2 to bootstrap an admin and verify them |
| `{"error": "QUANTITY_EXCEEDS_AVAILABLE"}` on a request that seems small enough | Other requests have already been ACCEPTED against this listing, reducing what's left | Check `GET /api/listings/<id>` — remaining = quantity minus already-accepted requests |
| `psycopg2.errors.InFailedSqlTransaction` in the terminal | A previous request in the same session errored mid-transaction | Restart `python run.py` — Flask-SQLAlchemy rolls back automatically per-request, this shouldn't persist, but a restart always clears it |

---

## 18b. Common Errors & Solutions — Phase 8

| Problem | Likely Cause | Fix |
|---|---|---|
| `{"error": "VALIDATION_ERROR"}` — "Both near_lat and near_lng must be provided together." | You passed only one of the two coordinate params | Always pass `near_lat` and `near_lng` together, or use `near_me=true` instead |
| `{"error": "VALIDATION_ERROR"}` — "near_me requires a profile with latitude/longitude on file." | `near_me=true` was used by an account with no provider/recipient profile, or a profile that was created without coordinates | Create/update your profile with `latitude`/`longitude` set (sections 8.1 / 11.1), or pass `near_lat`/`near_lng` explicitly instead |
| `GET /api/listings?near_lat=...` returns an empty list unexpectedly | `radius_km` is smaller than the actual distance, or the listing has no coordinates on file | Widen `radius_km`; check the listing's own `latitude`/`longitude` aren't `null` |
| `GET /api/providers/nearby-recipients` returns empty even though a recipient is nearby | That recipient hasn't been verified by an admin yet (section 14.2) | Only `verification_status: "verified"` recipients are eligible — unverified ones are intentionally excluded |
| `GET /api/recipients/nearby-providers` returns empty even though a provider is nearby | That provider's listings have all moved past `available` (e.g. `collected`, `cancelled`, `expired`) | This endpoint is about *current* availability, not just proximity — the provider needs at least one `available` listing |
| `{"error": "VALIDATION_ERROR"}` — "radius_km must be ... or less." / "greater than zero." | `radius_km` was negative, zero, or above the 500 km cap | Pass a positive value at or below 500 |

---

## 18c. Common Errors & Solutions — Phase 9

| Problem | Likely Cause | Fix |
|---|---|---|
| `{"error": "NOTIFICATION_NOT_FOUND"}` | Wrong notification ID | Check `GET /api/notifications` for the current user's actual notification IDs |
| `{"error": "FORBIDDEN"}` on `POST /api/notifications/<id>/read` | That notification belongs to a different user | Notifications are private — you can only read/mark your own |
| `GET /api/notifications` returns empty right after an event I expected to trigger one | Checking with the wrong account's token, or the event didn't actually happen yet (e.g. request still `pending`, not yet `accepted`) | Double-check which side (provider vs. recipient) receives that event — see the Phase 9 section above — and confirm the underlying action actually completed |
| `unread_count` doesn't match the visible list | You're viewing a page with `unread_only=false` (default) — `unread_count` counts *all* unread notifications, not just the current page | This is expected; use `?unread_only=true` to page through only the unread ones |

---

## 18d. Common Errors & Solutions — Phase 10

| Problem | Likely Cause | Fix |
|---|---|---|
| `{"error": "VALIDATION_ERROR"}` — "start_date must not be after end_date." | The two dates were swapped | Make sure `start_date` is chronologically before (or equal to) `end_date` |
| `{"error": "VALIDATION_ERROR"}` — "start_date must be a valid ISO-8601 date..." | Wrong date format | Use `YYYY-MM-DD`, e.g. `2026-09-10`, not a full datetime |
| `GET /api/reports/my-activity` returns `403 FORBIDDEN` | Called with an admin token | `/my-activity` is provider/recipient only by design — admins use `/platform-summary` and the scoped `/distributions/*` reports instead |
| `GET /api/reports/platform-summary` returns `403 FORBIDDEN` | Called with a non-admin token | This endpoint is admin-only |
| Passing `?provider_id=` as a provider doesn't change the results | Working as intended — providers/recipients are always pinned to their own data; that query param only has an effect for admin tokens | Use the admin account to view another provider's/recipient's numbers |
| `total_distributions` / `total_quantity` are `0` even though pickups were completed | A date filter excludes them, or the wrong account's token was used (which auto-scopes to that account) | Drop the date filters to check all-time; confirm you're using the token for the provider/recipient who was actually involved |

## 18e. Common Errors & Solutions — Phase 11

| Problem | Likely Cause | Fix |
|---|---|---|
| `{"error": "RATE_LIMITED"}`, `429` | More than 10 login attempts (or 5 register attempts) from the same caller within 5 minutes | Wait for the window in the `Retry-After` header (seconds) to pass, or use a different account/IP for further manual testing |
| `POST /api/admin/users/<id>/deactivate` returns `400` `CANNOT_DEACTIVATE_SELF` | The `<id>` in the URL is your own admin account | Use a second admin account, or target a different user's id |
| A deactivated user's existing token still seems to work | You're hitting a route that isn't behind `@token_required` (e.g. `GET /api/health`), or checking a cached response | Every protected route re-checks `AccountStatus` on every request via `token_required` — retry against a protected endpoint like `GET /api/profile` |
| `GET /api/admin/users` or `GET /api/audit-logs` returns `403 FORBIDDEN` | Called with a non-admin token | Both endpoints are admin-only by design |
| `{"error": "VALIDATION_ERROR"}` on `/api/admin/users?role=...` | `role`/`status` value isn't one of the accepted enum values | Use `provider`/`recipient`/`admin` for `role`, `active`/`inactive` for `status` |

---

## 19. What's Next (Phase 12 preview)

Phase 12 will introduce automated Testing:

- A `pytest` + `pytest-flask` test suite under `tests/`, covering the
  full request/pickup/distribution lifecycle, role-based access
  control, and the concurrency guarantees from Phase 6
- A dedicated test database/config (`TestingConfig` already exists in
  `app/config.py`, unused until now)
- Regression coverage for the security behaviors added in Phase 11
  (rate limiting, account deactivation taking effect immediately,
  admin-only route protection)

Phase 12 will only begin once Phase 11 has been reviewed and
confirmed working.

---

## Roadmap (all phases)

1. ✅ Flask Foundation
2. ✅ Database Design (PostgreSQL)
3. ✅ Authentication
4. ✅ Provider Module
5. ✅ Recipient Module
6. ✅ Request Workflow
7. ✅ Pickup and Distribution
8. ✅ Location-Based Search
9. ✅ Notifications
10. ✅ Reports
11. ✅ Security and Audit
12. ⬜ Testing
13. ⬜ Postman and Documentation
