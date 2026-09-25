"""
Recipient profile routes — mirrors app/routes/providers.py.

    POST /api/recipients/profile   — create my recipient profile
    PUT  /api/recipients/profile   — update my recipient profile
    GET  /api/recipients/profile   — view my recipient profile
"""

from flask import Blueprint, g, request

from app.auth.decorators import role_required, token_required
from app.models import UserRole
from app.services.geo_search_service import nearest_providers_with_availability
from app.services.recipient_service import (
    RecipientProfileError,
    create_recipient_profile,
    update_recipient_profile,
    verify_recipient_profile,
)
from app.utils.geo import validate_radius_km
from app.utils.pagination import get_pagination_params
from app.utils.responses import error_response, success_response

recipients_bp = Blueprint("recipients", __name__)


@recipients_bp.route("/profile", methods=["POST"])
@token_required
@role_required(UserRole.RECIPIENT)
def create_profile():
    """
    POST /api/recipients/profile

    Body:
        {
            "organization_name": "Hope Community Shelter",
            "contact_info": "+1 555-0200",
            "address": "88 Elm St",
            "city": "Springfield",
            "latitude": 39.801,
            "longitude": -89.650,
            "description": "Shelter serving 60 residents nightly."
        }

    New profiles start with verification_status = "pending" — an
    administrator must verify the organization (a later phase) before
    it can place food requests.
    """
    body = request.get_json(silent=True) or {}
    try:
        profile = create_recipient_profile(user=g.current_user, data=body)
    except RecipientProfileError as exc:
        return error_response(exc.message, exc.error_code, exc.status_code)

    return success_response(
        "Recipient profile created successfully. Pending verification.",
        data=profile.to_dict(),
        status_code=201,
    )


@recipients_bp.route("/profile", methods=["PUT"])
@token_required
@role_required(UserRole.RECIPIENT)
def update_profile():
    body = request.get_json(silent=True) or {}
    try:
        profile = update_recipient_profile(user=g.current_user, data=body)
    except RecipientProfileError as exc:
        return error_response(exc.message, exc.error_code, exc.status_code)

    return success_response(
        "Recipient profile updated successfully.", data=profile.to_dict()
    )


@recipients_bp.route("/profile", methods=["GET"])
@token_required
@role_required(UserRole.RECIPIENT)
def get_profile():
    profile = g.current_user.recipient_profile
    if profile is None:
        return error_response(
            "No recipient profile exists yet for this account.",
            "PROFILE_NOT_FOUND",
            404,
        )
    return success_response(
        "Recipient profile retrieved successfully.", data=profile.to_dict()
    )


@recipients_bp.route("/<int:profile_id>/verify", methods=["POST"])
@token_required
@role_required(UserRole.ADMIN)
def verify(profile_id):
    """
    POST /api/recipients/<id>/verify   (admin only)

    Minimal administrator action, introduced now because Phase 6
    (Request Workflow) requires a verified recipient in order to be
    testable at all. Broader user management, account activation/
    deactivation, and audit log access were added later, in Phase 11
    (see app/routes/admin.py and app/routes/audit.py).
    """
    try:
        profile = verify_recipient_profile(
            profile_id=profile_id, admin_user_id=g.current_user.id
        )
    except RecipientProfileError as exc:
        return error_response(exc.message, exc.error_code, exc.status_code)

    return success_response(
        "Recipient profile verified successfully.", data=profile.to_dict()
    )


@recipients_bp.route("/nearby-providers", methods=["GET"])
@token_required
@role_required(UserRole.RECIPIENT)
def nearby_providers():
    """
    GET /api/recipients/nearby-providers   (Phase 8)

    Providers near MY recipient profile's coordinates who currently
    have at least one AVAILABLE listing, nearest first. Requires my
    own recipient profile to already have latitude/longitude on file.

    Query parameters (all optional):
        radius_km   e.g. ?radius_km=15  (default 25, max 500)
        page, limit — standard pagination
    """
    profile = g.current_user.recipient_profile
    if profile is None:
        return error_response(
            "Complete your recipient profile before searching nearby providers.",
            "PROFILE_NOT_FOUND",
            404,
        )
    if profile.latitude is None or profile.longitude is None:
        return error_response(
            "Your recipient profile has no latitude/longitude on file yet.",
            "VALIDATION_ERROR",
            422,
        )

    radius_km, radius_error = validate_radius_km(request.args.get("radius_km"))
    if radius_error:
        return error_response(radius_error, "VALIDATION_ERROR", 422)

    page, limit = get_pagination_params(request.args)

    scored, pagination = nearest_providers_with_availability(
        near_lat=float(profile.latitude),
        near_lng=float(profile.longitude),
        radius_km=radius_km,
        page=page,
        limit=limit,
    )

    providers_data = []
    for provider_profile, distance_km in scored:
        item = provider_profile.to_dict()
        item["distance_km"] = round(distance_km, 2)
        providers_data.append(item)

    return success_response(
        "Nearby providers with available listings retrieved successfully.",
        data={"providers": providers_data, "pagination": pagination},
    )
