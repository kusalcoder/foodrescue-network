"""
Provider profile routes.

    POST /api/providers/profile   — create my provider profile
    PUT  /api/providers/profile   — update my provider profile
    GET  /api/providers/profile   — view my provider profile

All three require a logged-in PROVIDER (spec section 32 — role-level
authorization). There's no resource-level ownership check needed
here specifically because these routes only ever operate on "my own"
profile — `user.provider_profile`, derived from the token, never an
ID taken from the URL — so there's no other provider's profile a
caller could even address.
"""

from flask import Blueprint, g, request

from app.auth.decorators import role_required, token_required
from app.models import UserRole
from app.services.geo_search_service import nearest_verified_recipients
from app.services.provider_service import (
    ProviderProfileError,
    create_provider_profile,
    update_provider_profile,
)
from app.utils.geo import validate_radius_km
from app.utils.pagination import get_pagination_params
from app.utils.responses import error_response, success_response

providers_bp = Blueprint("providers", __name__)


@providers_bp.route("/profile", methods=["POST"])
@token_required
@role_required(UserRole.PROVIDER)
def create_profile():
    """
    POST /api/providers/profile

    Body:
        {
            "organization_name": "Green Table Restaurant",
            "contact_info": "+1 555-0100",
            "address": "12 Market St",
            "city": "Springfield",
            "latitude": 39.799999,
            "longitude": -89.644444,
            "description": "Family-owned Italian restaurant."
        }
    """
    body = request.get_json(silent=True) or {}
    try:
        profile = create_provider_profile(user=g.current_user, data=body)
    except ProviderProfileError as exc:
        return error_response(exc.message, exc.error_code, exc.status_code)

    return success_response(
        "Provider profile created successfully.",
        data=profile.to_dict(),
        status_code=201,
    )


@providers_bp.route("/profile", methods=["PUT"])
@token_required
@role_required(UserRole.PROVIDER)
def update_profile():
    """
    PUT /api/providers/profile

    Body: any subset of the fields accepted by create_profile above.
    Only fields present in the body are changed.
    """
    body = request.get_json(silent=True) or {}
    try:
        profile = update_provider_profile(user=g.current_user, data=body)
    except ProviderProfileError as exc:
        return error_response(exc.message, exc.error_code, exc.status_code)

    return success_response(
        "Provider profile updated successfully.", data=profile.to_dict()
    )


@providers_bp.route("/profile", methods=["GET"])
@token_required
@role_required(UserRole.PROVIDER)
def get_profile():
    """GET /api/providers/profile — view my own provider profile."""
    profile = g.current_user.provider_profile
    if profile is None:
        return error_response(
            "No provider profile exists yet for this account.",
            "PROFILE_NOT_FOUND",
            404,
        )
    return success_response("Provider profile retrieved successfully.", data=profile.to_dict())


@providers_bp.route("/nearby-recipients", methods=["GET"])
@token_required
@role_required(UserRole.PROVIDER)
def nearby_recipients():
    """
    GET /api/providers/nearby-recipients   (Phase 8)

    Verified recipient organizations near MY provider profile's
    coordinates, nearest first — e.g. to proactively reach out about
    a large surplus. Requires my own provider profile to already have
    latitude/longitude on file.

    Query parameters (all optional):
        radius_km   e.g. ?radius_km=15  (default 25, max 500)
        page, limit — standard pagination
    """
    profile = g.current_user.provider_profile
    if profile is None:
        return error_response(
            "Complete your provider profile before searching nearby recipients.",
            "PROFILE_NOT_FOUND",
            404,
        )
    if profile.latitude is None or profile.longitude is None:
        return error_response(
            "Your provider profile has no latitude/longitude on file yet.",
            "VALIDATION_ERROR",
            422,
        )

    radius_km, radius_error = validate_radius_km(request.args.get("radius_km"))
    if radius_error:
        return error_response(radius_error, "VALIDATION_ERROR", 422)

    page, limit = get_pagination_params(request.args)

    scored, pagination = nearest_verified_recipients(
        near_lat=float(profile.latitude),
        near_lng=float(profile.longitude),
        radius_km=radius_km,
        page=page,
        limit=limit,
    )

    recipients_data = []
    for recipient_profile, distance_km in scored:
        item = recipient_profile.to_dict()
        item["distance_km"] = round(distance_km, 2)
        recipients_data.append(item)

    return success_response(
        "Nearby verified recipients retrieved successfully.",
        data={"recipients": recipients_data, "pagination": pagination},
    )
