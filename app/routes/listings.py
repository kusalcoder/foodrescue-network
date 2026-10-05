"""
Food listing routes — provider-facing half.

    POST   /api/listings              — create a listing (provider only)
    PUT    /api/listings/<id>         — update MY listing (provider only, owner only)
    POST   /api/listings/<id>/cancel  — cancel MY listing (provider only, owner only)
    GET    /api/listings/mine         — view my own listings (provider only)
    GET    /api/listings/<id>         — view a single listing (any logged-in user)

Public/recipient-facing browsing, search, filtering, and pagination
across ALL listings (`GET /api/listings`) is built in Phase 5.
"""

from flask import Blueprint, g, request

from app.auth.decorators import role_required, token_required
from app.extensions import db
from app.models import FoodListing, UserRole
from app.services.listing_service import (
    ListingError,
    browse_listings_query,
    browse_listings_within_radius,
    cancel_listing,
    create_listing,
    get_owned_listing,
    list_own_listings,
    update_listing,
)
from app.services.request_service import RequestError, list_requests_for_listing
from app.utils.geo import validate_lat_lng, validate_radius_km
from app.utils.pagination import get_pagination_params, paginate_query
from app.utils.responses import error_response, success_response

listings_bp = Blueprint("listings", __name__)


def _require_provider_profile():
    """
    Shared guard: a PROVIDER user must have completed their provider
    profile (Phase 4's providers_bp) before they can own listings.
    Returns (profile, None) on success or (None, error_response) on
    failure, so routes can do:

        profile, err = _require_provider_profile()
        if err:
            return err
    """
    profile = g.current_user.provider_profile
    if profile is None:
        return None, error_response(
            "Complete your provider profile before creating listings.",
            "PROFILE_NOT_FOUND",
            404,
        )
    return profile, None


@listings_bp.route("", methods=["POST"])
@token_required
@role_required(UserRole.PROVIDER)
def create():
    """
    POST /api/listings

    Body:
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
    """
    profile, err = _require_provider_profile()
    if err:
        return err

    body = request.get_json(silent=True) or {}
    try:
        listing = create_listing(provider_profile=profile, data=body)
    except ListingError as exc:
        return error_response(exc.message, exc.error_code, exc.status_code)

    return success_response(
        "Food listing created successfully.",
        data=listing.to_dict(),
        status_code=201,
    )


@listings_bp.route("", methods=["GET"])
@token_required
def browse():
    """
    GET /api/listings

    Public browsing/search/filtering for any logged-in user (mainly
    recipients, but providers/admins can use it too). Only shows
    `available` listings whose pickup window hasn't passed, unless an
    explicit `status` filter is given.

    Query parameters (all optional):
        category        e.g. ?category=bakery
        city            e.g. ?city=springfield  (partial, case-insensitive)
        provider_id     e.g. ?provider_id=3
        available_date  e.g. ?available_date=2026-09-10
        status          e.g. ?status=available  (overrides the default)
        page            e.g. ?page=2      (default 1)
        limit           e.g. ?limit=10    (default from config, capped)

    Location-based search (Phase 8, spec preview section 19) — add
    any of these to sort/filter the results above by distance:
        near_lat, near_lng   e.g. ?near_lat=39.80&near_lng=-89.64
                             (must be supplied together)
        near_me=true         use MY OWN profile's coordinates instead
                             of passing near_lat/near_lng explicitly
                             (provider or recipient; 422 if my profile
                             has no coordinates on file)
        radius_km            e.g. ?radius_km=10  (default 25, max 500)
                             only meaningful alongside near_lat/near_lng
                             or near_me

    When a location search is active, each returned listing gains a
    `distance_km` field and results are ordered nearest-first instead
    of newest-first.

    Examples:
        GET /api/listings?category=bakery&city=springfield&page=1&limit=10
        GET /api/listings?near_lat=39.80&near_lng=-89.64&radius_km=10
        GET /api/listings?near_me=true&radius_km=10
    """
    filters = {
        "category": request.args.get("category"),
        "city": request.args.get("city"),
        "provider_id": request.args.get("provider_id"),
        "available_date": request.args.get("available_date"),
        "status": request.args.get("status"),
    }

    near_lat = request.args.get("near_lat")
    near_lng = request.args.get("near_lng")
    near_me = request.args.get("near_me", "").lower() == "true"

    if near_me:
        own_profile = g.current_user.provider_profile or g.current_user.recipient_profile
        if own_profile is None or own_profile.latitude is None or own_profile.longitude is None:
            return error_response(
                "near_me requires a profile with latitude/longitude on file.",
                "VALIDATION_ERROR",
                422,
            )
        near_lat = own_profile.latitude
        near_lng = own_profile.longitude
    else:
        coord_error = validate_lat_lng(near_lat, near_lng, field_prefix="near")
        if coord_error:
            return error_response(coord_error, "VALIDATION_ERROR", 422)

    try:
        query = browse_listings_query(filters=filters)
    except ListingError as exc:
        return error_response(exc.message, exc.error_code, exc.status_code)

    page, limit = get_pagination_params(request.args)

    if near_lat is not None and near_lng is not None:
        radius_km, radius_error = validate_radius_km(request.args.get("radius_km"))
        if radius_error:
            return error_response(radius_error, "VALIDATION_ERROR", 422)

        scored_listings, pagination = browse_listings_within_radius(
            query=query,
            near_lat=float(near_lat),
            near_lng=float(near_lng),
            radius_km=radius_km,
            page=page,
            limit=limit,
        )
        listings_data = []
        for listing, distance_km in scored_listings:
            item = listing.to_dict()
            item["distance_km"] = round(distance_km, 2)
            listings_data.append(item)
    else:
        listings, pagination = paginate_query(query, page, limit)
        listings_data = [listing.to_dict() for listing in listings]

    return success_response(
        "Listings retrieved successfully.",
        data={
            "listings": listings_data,
            "pagination": pagination,
        },
    )


@listings_bp.route("/mine", methods=["GET"])
@token_required
@role_required(UserRole.PROVIDER)
def mine():
    """GET /api/listings/mine — every listing owned by the current provider."""
    profile, err = _require_provider_profile()
    if err:
        return err

    listings = list_own_listings(provider_profile=profile)
    return success_response(
        "Listings retrieved successfully.",
        data=[listing.to_dict() for listing in listings],
    )


@listings_bp.route("/<int:listing_id>", methods=["GET"])
@token_required
def get_one(listing_id):
    """
    GET /api/listings/<id>

    Any logged-in user can view a single listing's details — this is
    the "view listing details" step before a recipient requests it
    (Phase 6). Full public browsing/search is Phase 5.
    """
    listing = db.session.get(FoodListing, listing_id)
    if listing is None:
        return error_response("Listing not found.", "LISTING_NOT_FOUND", 404)
    return success_response("Listing retrieved successfully.", data=listing.to_dict())


@listings_bp.route("/<int:listing_id>", methods=["PUT"])
@token_required
@role_required(UserRole.PROVIDER)
def update(listing_id):
    """PUT /api/listings/<id> — update a listing you own."""
    profile, err = _require_provider_profile()
    if err:
        return err

    body = request.get_json(silent=True) or {}
    try:
        listing = update_listing(
            listing_id=listing_id, provider_profile=profile, data=body
        )
    except ListingError as exc:
        return error_response(exc.message, exc.error_code, exc.status_code)

    return success_response("Listing updated successfully.", data=listing.to_dict())


@listings_bp.route("/<int:listing_id>/cancel", methods=["POST"])
@token_required
@role_required(UserRole.PROVIDER)
def cancel(listing_id):
    """POST /api/listings/<id>/cancel — cancel a listing you own."""
    profile, err = _require_provider_profile()
    if err:
        return err

    try:
        listing = cancel_listing(listing_id=listing_id, provider_profile=profile)
    except ListingError as exc:
        return error_response(exc.message, exc.error_code, exc.status_code)

    return success_response("Listing cancelled successfully.", data=listing.to_dict())


@listings_bp.route("/<int:listing_id>/requests", methods=["GET"])
@token_required
@role_required(UserRole.PROVIDER)
def requests_for_listing(listing_id):
    """
    GET /api/listings/<id>/requests

    All requests submitted against this listing — provider only, and
    only for a listing they own.
    """
    profile, err = _require_provider_profile()
    if err:
        return err

    try:
        reqs = list_requests_for_listing(listing_id=listing_id, provider_profile=profile)
    except RequestError as exc:
        return error_response(exc.message, exc.error_code, exc.status_code)

    return success_response(
        "Requests retrieved successfully.", data=[r.to_dict() for r in reqs]
    )
