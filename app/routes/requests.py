"""
Food request routes.

    POST /api/requests              — submit a request (recipient only)
    GET  /api/requests               — my own requests (recipient only)
    GET  /api/requests/<id>          — view one request (owning recipient OR owning provider)
    POST /api/requests/<id>/accept   — accept (provider only, must own the listing)
    POST /api/requests/<id>/reject   — reject (provider only, must own the listing)
    POST /api/requests/<id>/cancel   — cancel (recipient only, must own the request)
    POST /api/requests/<id>/schedule-pickup — schedule a pickup (provider only,
                                        must own the listing; request must be
                                        accepted) — see Phase 7,
                                        app/services/pickup_service.py.

    GET /api/listings/<id>/requests  — all requests for a listing (provider only,
                                        must own the listing) — registered on
                                        listings_bp since the resource in the URL
                                        is a listing, not a request.
"""

from flask import Blueprint, g, request

from app.auth.decorators import role_required, token_required
from app.models import UserRole
from app.services.pickup_service import PickupError, schedule_pickup
from app.services.request_service import (
    RequestError,
    accept_request,
    cancel_request,
    create_request,
    get_request_for_viewer,
    list_requests_for_recipient,
    reject_request,
)
from app.utils.responses import error_response, success_response

requests_bp = Blueprint("requests", __name__)


def _require_recipient_profile():
    profile = g.current_user.recipient_profile
    if profile is None:
        return None, error_response(
            "Complete your recipient profile before requesting food.",
            "PROFILE_NOT_FOUND",
            404,
        )
    return profile, None


def _require_provider_profile():
    profile = g.current_user.provider_profile
    if profile is None:
        return None, error_response(
            "Complete your provider profile first.", "PROFILE_NOT_FOUND", 404
        )
    return profile, None


@requests_bp.route("", methods=["POST"])
@token_required
@role_required(UserRole.RECIPIENT)
def create():
    """
    POST /api/requests

    Body:
        {
            "listing_id": 1,
            "requested_quantity": 20,
            "request_message": "We can pick up any time after 5pm."
        }
    """
    profile, err = _require_recipient_profile()
    if err:
        return err

    body = request.get_json(silent=True) or {}
    try:
        req = create_request(recipient_profile=profile, data=body)
    except RequestError as exc:
        return error_response(exc.message, exc.error_code, exc.status_code)

    return success_response(
        "Request submitted successfully.", data=req.to_dict(), status_code=201
    )


@requests_bp.route("", methods=["GET"])
@token_required
@role_required(UserRole.RECIPIENT)
def mine():
    """GET /api/requests — every request I (the recipient) have made."""
    profile, err = _require_recipient_profile()
    if err:
        return err

    reqs = list_requests_for_recipient(recipient_profile=profile)
    return success_response(
        "Requests retrieved successfully.", data=[r.to_dict() for r in reqs]
    )


@requests_bp.route("/<int:request_id>", methods=["GET"])
@token_required
def get_one(request_id):
    """GET /api/requests/<id> — owning recipient or owning provider only."""
    try:
        req = get_request_for_viewer(request_id=request_id, current_user=g.current_user)
    except RequestError as exc:
        return error_response(exc.message, exc.error_code, exc.status_code)

    return success_response("Request retrieved successfully.", data=req.to_dict())


@requests_bp.route("/<int:request_id>/accept", methods=["POST"])
@token_required
@role_required(UserRole.PROVIDER)
def accept(request_id):
    profile, err = _require_provider_profile()
    if err:
        return err

    try:
        req = accept_request(request_id=request_id, provider_profile=profile)
    except RequestError as exc:
        return error_response(exc.message, exc.error_code, exc.status_code)

    return success_response("Request accepted successfully.", data=req.to_dict())


@requests_bp.route("/<int:request_id>/reject", methods=["POST"])
@token_required
@role_required(UserRole.PROVIDER)
def reject(request_id):
    profile, err = _require_provider_profile()
    if err:
        return err

    try:
        req = reject_request(request_id=request_id, provider_profile=profile)
    except RequestError as exc:
        return error_response(exc.message, exc.error_code, exc.status_code)

    return success_response("Request rejected successfully.", data=req.to_dict())


@requests_bp.route("/<int:request_id>/cancel", methods=["POST"])
@token_required
@role_required(UserRole.RECIPIENT)
def cancel(request_id):
    profile, err = _require_recipient_profile()
    if err:
        return err

    try:
        req = cancel_request(request_id=request_id, recipient_profile=profile)
    except RequestError as exc:
        return error_response(exc.message, exc.error_code, exc.status_code)

    return success_response("Request cancelled successfully.", data=req.to_dict())


@requests_bp.route("/<int:request_id>/schedule-pickup", methods=["POST"])
@token_required
@role_required(UserRole.PROVIDER)
def schedule_pickup_for_request(request_id):
    """
    POST /api/requests/<id>/schedule-pickup

    Body (all optional):
        {"pickup_time": "2026-09-10T18:00:00+00:00", "confirmation_info": "..."}
    """
    profile, err = _require_provider_profile()
    if err:
        return err

    body = request.get_json(silent=True) or {}
    try:
        pickup = schedule_pickup(
            request_id=request_id, provider_profile=profile, data=body
        )
    except PickupError as exc:
        return error_response(exc.message, exc.error_code, exc.status_code)

    return success_response(
        "Pickup scheduled successfully.", data=pickup.to_dict(), status_code=201
    )
