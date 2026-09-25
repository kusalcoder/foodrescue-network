"""
Food listing business logic — the provider-facing half (create,
update, cancel, view own). Recipient-facing browsing/search/filtering
is built in Phase 5 on top of the same `FoodListing` model.
"""

import math
from datetime import date, datetime

from app.extensions import db
from app.models import FoodCategory, FoodListing, ListingStatus, ProviderProfile
from app.models.base import utcnow
from app.utils.audit import record_audit_log
from app.utils.geo import haversine_km
from app.utils.validation import validate_coordinates, validate_positive_number

VALID_CATEGORIES = {c.value for c in FoodCategory}


class ListingError(Exception):
    def __init__(self, message: str, error_code: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code


def _parse_datetime(value, field_name):
    if value is None:
        raise ListingError(f"{field_name} is required.", "VALIDATION_ERROR", 422)
    try:
        # Accepts ISO-8601, e.g. "2026-09-10T17:00:00+00:00"
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ListingError(
            f"{field_name} must be a valid ISO-8601 datetime.",
            "VALIDATION_ERROR",
            422,
        )


def _parse_date(value, field_name):
    if value is None:
        raise ListingError(f"{field_name} is required.", "VALIDATION_ERROR", 422)
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ListingError(
            f"{field_name} must be a valid ISO-8601 date (YYYY-MM-DD).",
            "VALIDATION_ERROR",
            422,
        )


def _validate_listing_fields(data: dict):
    if not data.get("food_name") or not str(data.get("food_name")).strip():
        raise ListingError("Food name is required.", "VALIDATION_ERROR", 422)

    category = data.get("category")
    if category not in VALID_CATEGORIES:
        raise ListingError(
            f"Category must be one of: {', '.join(sorted(VALID_CATEGORIES))}.",
            "VALIDATION_ERROR",
            422,
        )

    qty_error = validate_positive_number(data.get("quantity"), "Quantity")
    if qty_error:
        raise ListingError(qty_error, "VALIDATION_ERROR", 422)

    if not data.get("quantity_unit") or not str(data.get("quantity_unit")).strip():
        raise ListingError("Quantity unit is required.", "VALIDATION_ERROR", 422)

    if not data.get("pickup_location") or not str(data.get("pickup_location")).strip():
        raise ListingError("Pickup location is required.", "VALIDATION_ERROR", 422)

    coord_error = validate_coordinates(data.get("latitude"), data.get("longitude"))
    if coord_error:
        raise ListingError(coord_error, "VALIDATION_ERROR", 422)

    available_date = _parse_date(data.get("available_date"), "available_date")
    pickup_start = _parse_datetime(data.get("pickup_start_time"), "pickup_start_time")
    pickup_end = _parse_datetime(data.get("pickup_end_time"), "pickup_end_time")

    if pickup_end <= pickup_start:
        raise ListingError(
            "pickup_end_time must be after pickup_start_time.",
            "VALIDATION_ERROR",
            422,
        )

    return available_date, pickup_start, pickup_end


def create_listing(*, provider_profile, data: dict) -> FoodListing:
    """
    Create a new food listing owned by `provider_profile`.

    Requires the caller to already have a ProviderProfile — enforced
    by the route before this is even called (see routes/listings.py).
    """
    available_date, pickup_start, pickup_end = _validate_listing_fields(data)

    listing = FoodListing(
        provider_id=provider_profile.id,
        food_name=data["food_name"].strip(),
        description=data.get("description"),
        category=FoodCategory(data["category"]),
        quantity=data["quantity"],
        quantity_unit=data["quantity_unit"].strip(),
        available_date=available_date,
        pickup_start_time=pickup_start,
        pickup_end_time=pickup_end,
        pickup_location=data["pickup_location"].strip(),
        latitude=data.get("latitude"),
        longitude=data.get("longitude"),
        conditions=data.get("conditions"),
        status=ListingStatus.AVAILABLE,
    )
    db.session.add(listing)
    db.session.flush()

    record_audit_log(
        user_id=provider_profile.user_id,
        action="listing_created",
        resource_type="food_listing",
        resource_id=listing.id,
        description=f"Listing {listing.food_name!r} created.",
    )
    db.session.commit()
    return listing


def _require_owned_listing(listing_id: int, provider_profile) -> FoodListing:
    listing = db.session.get(FoodListing, listing_id)
    if listing is None:
        raise ListingError("Listing not found.", "LISTING_NOT_FOUND", 404)
    if listing.provider_id != provider_profile.id:
        # Resource-level authorization (spec section 32): being a
        # provider isn't enough — it must be YOUR listing.
        raise ListingError(
            "You do not have permission to modify this listing.",
            "FORBIDDEN",
            403,
        )
    return listing


def update_listing(*, listing_id: int, provider_profile, data: dict) -> FoodListing:
    listing = _require_owned_listing(listing_id, provider_profile)

    if listing.status not in (ListingStatus.AVAILABLE,):
        # Rule: once a listing has moved past "available" (reserved,
        # pickup pending, collected, expired, cancelled), its core
        # details shouldn't be edited out from under an in-progress
        # request. A provider who needs to change something at that
        # point should cancel and create a new listing instead.
        raise ListingError(
            "Only listings with status 'available' can be edited.",
            "INVALID_LISTING_STATE",
            409,
        )

    merged = {
        "food_name": data.get("food_name", listing.food_name),
        "category": data.get("category", listing.category.value),
        "quantity": data.get("quantity", listing.quantity),
        "quantity_unit": data.get("quantity_unit", listing.quantity_unit),
        "pickup_location": data.get("pickup_location", listing.pickup_location),
        "latitude": data.get("latitude", listing.latitude),
        "longitude": data.get("longitude", listing.longitude),
        "available_date": data.get(
            "available_date", listing.available_date.isoformat()
        ),
        "pickup_start_time": data.get(
            "pickup_start_time", listing.pickup_start_time.isoformat()
        ),
        "pickup_end_time": data.get(
            "pickup_end_time", listing.pickup_end_time.isoformat()
        ),
    }
    available_date, pickup_start, pickup_end = _validate_listing_fields(merged)

    listing.food_name = merged["food_name"].strip()
    listing.description = data.get("description", listing.description)
    listing.category = FoodCategory(merged["category"])
    listing.quantity = merged["quantity"]
    listing.quantity_unit = merged["quantity_unit"].strip()
    listing.available_date = available_date
    listing.pickup_start_time = pickup_start
    listing.pickup_end_time = pickup_end
    listing.pickup_location = merged["pickup_location"].strip()
    listing.latitude = merged["latitude"]
    listing.longitude = merged["longitude"]
    listing.conditions = data.get("conditions", listing.conditions)

    record_audit_log(
        user_id=provider_profile.user_id,
        action="listing_updated",
        resource_type="food_listing",
        resource_id=listing.id,
        description=f"Listing {listing.id} updated.",
    )
    db.session.commit()
    return listing


def cancel_listing(*, listing_id: int, provider_profile) -> FoodListing:
    listing = _require_owned_listing(listing_id, provider_profile)

    if listing.status != ListingStatus.AVAILABLE:
        # Rule: can't cancel a listing that's already reserved,
        # pickup-pending, collected, expired, or already cancelled.
        # (Reserved/pending listings have an active request against
        # them — that request's own cancel/reject flow, built in
        # Phase 6, is the correct path at that point.)
        raise ListingError(
            "Only listings with status 'available' can be cancelled.",
            "INVALID_LISTING_STATE",
            409,
        )

    listing.status = ListingStatus.CANCELLED

    record_audit_log(
        user_id=provider_profile.user_id,
        action="listing_cancelled",
        resource_type="food_listing",
        resource_id=listing.id,
        description=f"Listing {listing.id} cancelled by provider.",
    )
    db.session.commit()
    return listing


def get_owned_listing(*, listing_id: int, provider_profile) -> FoodListing:
    return _require_owned_listing(listing_id, provider_profile)


def list_own_listings(*, provider_profile):
    return (
        db.session.query(FoodListing)
        .filter_by(provider_id=provider_profile.id)
        .order_by(FoodListing.created_at.desc())
        .all()
    )


def browse_listings_query(*, filters: dict):
    """
    Build (but don't execute) the SQLAlchemy query for public/
    recipient browsing (spec sections 18/20).

    By default, only shows listings that are:
        - status = AVAILABLE (nothing reserved/collected/cancelled/expired)
        - pickup_end_time still in the future (a simple, always-on
          safety net so listings that should already be expired never
          show up while waiting for a dedicated expiry sweep, added
          in a later phase)

    Supported filters (all optional):
        category      — exact match against FoodCategory value
        city           — case-insensitive match against the
                         provider's city
        provider_id    — exact match
        available_date — exact date (YYYY-MM-DD)
        status         — override the default AVAILABLE-only filter
                         (e.g. an admin reviewing all statuses)

    Returns a SQLAlchemy Query object; the caller applies pagination
    and ordering-independent concerns on top (see paginate_query).
    """
    query = db.session.query(FoodListing).join(
        ProviderProfile, FoodListing.provider_id == ProviderProfile.id
    )

    status_filter = filters.get("status")
    if status_filter:
        if status_filter not in {s.value for s in ListingStatus}:
            raise ListingError(
                f"Status must be one of: {', '.join(s.value for s in ListingStatus)}.",
                "VALIDATION_ERROR",
                422,
            )
        query = query.filter(FoodListing.status == ListingStatus(status_filter))
    else:
        query = query.filter(FoodListing.status == ListingStatus.AVAILABLE)
        query = query.filter(FoodListing.pickup_end_time > utcnow())

    category = filters.get("category")
    if category:
        if category not in VALID_CATEGORIES:
            raise ListingError(
                f"Category must be one of: {', '.join(sorted(VALID_CATEGORIES))}.",
                "VALIDATION_ERROR",
                422,
            )
        query = query.filter(FoodListing.category == FoodCategory(category))

    city = filters.get("city")
    if city:
        query = query.filter(ProviderProfile.city.ilike(f"%{city.strip()}%"))

    provider_id = filters.get("provider_id")
    if provider_id:
        try:
            query = query.filter(FoodListing.provider_id == int(provider_id))
        except (TypeError, ValueError):
            raise ListingError(
                "provider_id must be an integer.", "VALIDATION_ERROR", 422
            )

    available_date = filters.get("available_date")
    if available_date:
        parsed = _parse_date(available_date, "available_date")
        query = query.filter(FoodListing.available_date == parsed)

    return query.order_by(FoodListing.created_at.desc())


def browse_listings_within_radius(
    *, query, near_lat: float, near_lng: float, radius_km: float, page: int, limit: int
):
    """
    Location-based search (Phase 8, spec preview section 19).

    Takes an already status/category/city/etc.-filtered (but not yet
    paginated) listings `query` — normally the result of
    `browse_listings_query` — and narrows/orders it by distance from
    (near_lat, near_lng):

        - listings with no coordinates are dropped (there's nothing
          to measure distance from)
        - listings farther than `radius_km` are dropped
        - the remainder is sorted nearest-first

    Distance filtering isn't pushed into the SQL WHERE clause because
    that needs either a spatial extension (PostGIS) or hand-rolled
    trig in raw SQL. For this project's scale — a directory-sized
    listings table, not a national dataset — it's cheap enough to let
    the normal indexed query narrow things down by status/category
    first, then finish the distance filter/sort/pagination here in
    Python.

    Returns (page_items, pagination_metadata), where each page item
    is a (FoodListing, distance_km) tuple — mirroring the shape of
    `app.utils.pagination.paginate_query` so routes can handle both
    the same way, just adding a `distance_km` field per item.
    """
    candidates = query.all()

    scored = []
    for listing in candidates:
        if listing.latitude is None or listing.longitude is None:
            continue
        distance_km = haversine_km(
            near_lat, near_lng, float(listing.latitude), float(listing.longitude)
        )
        if distance_km <= radius_km:
            scored.append((listing, distance_km))

    scored.sort(key=lambda pair: pair[1])

    total = len(scored)
    total_pages = math.ceil(total / limit) if total else 0
    start = (page - 1) * limit
    page_items = scored[start : start + limit]

    metadata = {"page": page, "limit": limit, "total": total, "total_pages": total_pages}
    return page_items, metadata
