"""
Pickup routes.

    GET  /api/pickups             — my own pickups (provider or recipient)
    GET  /api/pickups/<id>        — view one (owning provider OR owning recipient)
    POST /api/pickups/<id>/confirm  — recipient confirms a scheduled pickup
    POST /api/pickups/<id>/complete — provider marks the handover complete
    POST /api/pickups/<id>/fail     — provider marks a no-show/failed pickup
    POST /api/pickups/<id>/cancel   — recipient cancels a pickup they can't make

Scheduling a pickup is registered on `requests_bp` instead (the
resource in that URL is a request, not yet a pickup — see
`POST /api/requests/<id>/schedule-pickup` in app/routes/requests.py).
"""

from flask import Blueprint, g, request

from app.auth.decorators import role_required, token_required
from app.models import UserRole
from app.services.pickup_service import (
    PickupError,
    cancel_pickup,
    complete_pickup,
    confirm_pickup,
    fail_pickup,
    get_pickup_for_viewer,
    list_pickups_query,
)
from app.utils.pagination import get_pagination_params, paginate_query
from app.utils.responses import error_response, success_response

pickups_bp = Blueprint("pickups", __name__)


def _require_provider_profile():
    profile = g.current_user.provider_profile
    if profile is None:
        return None, error_response(
            "Complete your provider profile first.", "PROFILE_NOT_FOUND", 404
        )
    return profile, None


def _require_recipient_profile():
    profile = g.current_user.recipient_profile
    if profile is None:
        return None, error_response(
            "Complete your recipient profile first.", "PROFILE_NOT_FOUND", 404
        )
    return profile, None


@pickups_bp.route("", methods=["GET"])
@token_required
@role_required(UserRole.PROVIDER, UserRole.RECIPIENT)
def mine():
    """
    GET /api/pickups — every pickup involving me, as either the
    provider or the recipient (whichever profile(s) I have).

    Query parameters (optional): page, limit.
    """
    query = list_pickups_query(current_user=g.current_user)
    if query is None:
        return error_response(
            "Complete a provider or recipient profile first.",
            "PROFILE_NOT_FOUND",
            404,
        )

    page, limit = get_pagination_params(request.args)
    items, pagination = paginate_query(query, page, limit)
    return success_response(
        "Pickups retrieved successfully.",
        data={"pickups": [p.to_dict() for p in items], "pagination": pagination},
    )


@pickups_bp.route("/<int:pickup_id>", methods=["GET"])
@token_required
def get_one(pickup_id):
    """GET /api/pickups/<id> — owning provider or owning recipient only."""
    try:
        pickup = get_pickup_for_viewer(pickup_id=pickup_id, current_user=g.current_user)
    except PickupError as exc:
        return error_response(exc.message, exc.error_code, exc.status_code)

    return success_response("Pickup retrieved successfully.", data=pickup.to_dict())


@pickups_bp.route("/<int:pickup_id>/confirm", methods=["POST"])
@token_required
@role_required(UserRole.RECIPIENT)
def confirm(pickup_id):
    profile, err = _require_recipient_profile()
    if err:
        return err

    try:
        pickup = confirm_pickup(pickup_id=pickup_id, recipient_profile=profile)
    except PickupError as exc:
        return error_response(exc.message, exc.error_code, exc.status_code)

    return success_response("Pickup confirmed successfully.", data=pickup.to_dict())


@pickups_bp.route("/<int:pickup_id>/complete", methods=["POST"])
@token_required
@role_required(UserRole.PROVIDER)
def complete(pickup_id):
    """
    POST /api/pickups/<id>/complete

    Body (all optional):
        {"pickup_time": "2026-09-10T18:05:00+00:00", "confirmation_info": "Signed by J. Doe"}
    """
    profile, err = _require_provider_profile()
    if err:
        return err

    body = request.get_json(silent=True) or {}
    try:
        pickup = complete_pickup(pickup_id=pickup_id, provider_profile=profile, data=body)
    except PickupError as exc:
        return error_response(exc.message, exc.error_code, exc.status_code)

    return success_response("Pickup completed successfully.", data=pickup.to_dict())


@pickups_bp.route("/<int:pickup_id>/fail", methods=["POST"])
@token_required
@role_required(UserRole.PROVIDER)
def fail(pickup_id):
    """
    POST /api/pickups/<id>/fail

    Body (optional): {"reason": "Recipient did not show up."}
    """
    profile, err = _require_provider_profile()
    if err:
        return err

    body = request.get_json(silent=True) or {}
    try:
        pickup = fail_pickup(pickup_id=pickup_id, provider_profile=profile, data=body)
    except PickupError as exc:
        return error_response(exc.message, exc.error_code, exc.status_code)

    return success_response("Pickup marked as failed.", data=pickup.to_dict())


@pickups_bp.route("/<int:pickup_id>/cancel", methods=["POST"])
@token_required
@role_required(UserRole.RECIPIENT)
def cancel(pickup_id):
    profile, err = _require_recipient_profile()
    if err:
        return err

    try:
        pickup = cancel_pickup(pickup_id=pickup_id, recipient_profile=profile)
    except PickupError as exc:
        return error_response(exc.message, exc.error_code, exc.status_code)

    return success_response("Pickup cancelled successfully.", data=pickup.to_dict())
