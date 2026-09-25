"""
Pickup scheduling, confirmation, and completion business logic
(Phase 7 — spec sections 16-18).

This picks up exactly where Phase 6 left off: `FoodRequest.status`
can reach ACCEPTED, but nothing in Phase 6 could ever move it past
that. Phase 7 adds the two remaining transitions:

    ACCEPTED -> PICKUP_PENDING -> COMPLETED

A `PickupRecord` is created the moment a pickup is scheduled (one
request has at most one *active* pickup record at a time — if a
pickup fails, we keep that failed row for history and require a new
one to be scheduled rather than reusing it). Its own lifecycle is
independent of the request's:

    SCHEDULED -> CONFIRMED -> COMPLETED
              \\-> FAILED
              \\-> CANCELLED

Only COMPLETED pickups ever produce a `DistributionRecord` — that
table is the permanent, append-only history of food that actually
changed hands (spec section 17 / rule #6), so it must never be
written for a pickup that was merely scheduled or confirmed.

Who does what:
    - The PROVIDER schedules a pickup for a request they've accepted
      (they're the one who knows when their location can hand the
      food over), marks it completed once the handover happens, and
      can mark it failed (e.g. a no-show).
    - The RECIPIENT confirms a scheduled pickup (acknowledging the
      time works for them) before the provider completes it.

Listing status bookkeeping: a listing can have several concurrently
ACCEPTED requests (spec section 15's split-quantity example), so
completing one pickup should only flip the listing to COLLECTED once
*every* accepted claim against it has been picked up — otherwise it
stays exactly as Phase 6 already left it (AVAILABLE or RESERVED).
"""

from datetime import datetime

from app.extensions import db
from app.models import (
    DistributionRecord,
    FoodListing,
    FoodRequest,
    ListingStatus,
    PickupRecord,
    PickupStatus,
    RequestStatus,
)
from app.models.base import utcnow
from app.services.notification_service import create_notification
from app.utils.audit import record_audit_log

ACTIVE_PICKUP_STATUSES = (PickupStatus.SCHEDULED, PickupStatus.CONFIRMED)


class PickupError(Exception):
    def __init__(self, message: str, error_code: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code


def _parse_optional_datetime(value, field_name):
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise PickupError(
            f"{field_name} must be a valid ISO-8601 datetime.",
            "VALIDATION_ERROR",
            422,
        )


def _require_pickup(pickup_id: int) -> PickupRecord:
    pickup = db.session.get(PickupRecord, pickup_id)
    if pickup is None:
        raise PickupError("Pickup record not found.", "PICKUP_NOT_FOUND", 404)
    return pickup


def _no_other_active_claims(listing_id: int, exclude_request_id: int) -> bool:
    """
    True if no other request against this listing is still
    ACCEPTED or PICKUP_PENDING (i.e. every claim on the listing has
    now reached a terminal state — COMPLETED, REJECTED, or
    CANCELLED). Used to decide whether the whole listing can be
    marked COLLECTED.
    """
    other_active = (
        db.session.query(FoodRequest.id)
        .filter(
            FoodRequest.listing_id == listing_id,
            FoodRequest.id != exclude_request_id,
            FoodRequest.status.in_(
                [RequestStatus.ACCEPTED, RequestStatus.PICKUP_PENDING]
            ),
        )
        .first()
    )
    return other_active is None


def schedule_pickup(*, request_id: int, provider_profile, data: dict) -> PickupRecord:
    """
    Provider schedules a pickup for a request they've accepted.

    Body (all optional):
        {"pickup_time": "2026-09-10T18:00:00+00:00", "confirmation_info": "..."}
    """
    food_request = db.session.get(FoodRequest, request_id)
    if food_request is None:
        raise PickupError("Request not found.", "REQUEST_NOT_FOUND", 404)

    listing = db.session.get(FoodListing, food_request.listing_id)

    if listing.provider_id != provider_profile.id:
        raise PickupError(
            "You do not have permission to schedule pickup for this request.",
            "FORBIDDEN",
            403,
        )

    if food_request.status != RequestStatus.ACCEPTED:
        raise PickupError(
            f"Only accepted requests can have a pickup scheduled (current status: "
            f"{food_request.status.value}).",
            "INVALID_REQUEST_STATE",
            409,
        )

    existing_active = (
        db.session.query(PickupRecord.id)
        .filter(
            PickupRecord.request_id == food_request.id,
            PickupRecord.status.in_(ACTIVE_PICKUP_STATUSES),
        )
        .first()
    )
    if existing_active is not None:
        raise PickupError(
            "A pickup is already scheduled for this request.",
            "PICKUP_ALREADY_SCHEDULED",
            409,
        )

    pickup_time = _parse_optional_datetime(data.get("pickup_time"), "pickup_time")

    pickup = PickupRecord(
        request_id=food_request.id,
        listing_id=listing.id,
        provider_id=listing.provider_id,
        recipient_id=food_request.recipient_id,
        pickup_time=pickup_time,
        status=PickupStatus.SCHEDULED,
        confirmation_info=data.get("confirmation_info"),
    )
    db.session.add(pickup)

    food_request.status = RequestStatus.PICKUP_PENDING

    db.session.flush()
    record_audit_log(
        user_id=provider_profile.user_id,
        action="pickup_scheduled",
        resource_type="pickup_record",
        resource_id=pickup.id,
        description=f"Pickup scheduled for request {food_request.id}.",
    )
    create_notification(
        user_id=food_request.recipient.user_id,
        notification_type="pickup_scheduled",
        title="Pickup scheduled",
        message=f"A pickup was scheduled for your request on {listing.food_name!r}.",
        related_resource_type="pickup_record",
        related_resource_id=pickup.id,
    )
    db.session.commit()
    return pickup


def confirm_pickup(*, pickup_id: int, recipient_profile) -> PickupRecord:
    """Recipient confirms a scheduled pickup time works for them."""
    pickup = _require_pickup(pickup_id)

    if pickup.recipient_id != recipient_profile.id:
        raise PickupError(
            "You do not have permission to confirm this pickup.", "FORBIDDEN", 403
        )

    if pickup.status != PickupStatus.SCHEDULED:
        raise PickupError(
            f"Only scheduled pickups can be confirmed (current status: "
            f"{pickup.status.value}).",
            "INVALID_PICKUP_STATE",
            409,
        )

    pickup.status = PickupStatus.CONFIRMED

    record_audit_log(
        user_id=recipient_profile.user_id,
        action="pickup_confirmed",
        resource_type="pickup_record",
        resource_id=pickup.id,
        description=f"Pickup {pickup.id} confirmed by recipient.",
    )
    create_notification(
        user_id=pickup.provider.user_id,
        notification_type="pickup_confirmed",
        title="Pickup confirmed",
        message=f"The recipient confirmed pickup {pickup.id}.",
        related_resource_type="pickup_record",
        related_resource_id=pickup.id,
    )
    db.session.commit()
    return pickup


def complete_pickup(*, pickup_id: int, provider_profile, data: dict) -> PickupRecord:
    """
    Provider marks the handover as having actually happened. This is
    the one place in the whole system that creates a
    `DistributionRecord` — the permanent, append-only proof that food
    changed hands.
    """
    pickup = _require_pickup(pickup_id)

    if pickup.provider_id != provider_profile.id:
        raise PickupError(
            "You do not have permission to complete this pickup.", "FORBIDDEN", 403
        )

    if pickup.status not in ACTIVE_PICKUP_STATUSES:
        raise PickupError(
            f"Only scheduled or confirmed pickups can be completed (current status: "
            f"{pickup.status.value}).",
            "INVALID_PICKUP_STATE",
            409,
        )

    actual_time = _parse_optional_datetime(data.get("pickup_time"), "pickup_time")
    pickup.pickup_time = actual_time or pickup.pickup_time or utcnow()
    pickup.status = PickupStatus.COMPLETED
    if data.get("confirmation_info") is not None:
        pickup.confirmation_info = data["confirmation_info"]

    food_request = pickup.request
    food_request.status = RequestStatus.COMPLETED

    listing = pickup.listing
    distribution = DistributionRecord(
        listing_id=listing.id,
        provider_id=pickup.provider_id,
        recipient_id=pickup.recipient_id,
        pickup_record_id=pickup.id,
        quantity=food_request.requested_quantity,
        pickup_datetime=pickup.pickup_time,
        food_category=listing.category.value,
        completion_status="completed",
    )
    db.session.add(distribution)

    if _no_other_active_claims(listing.id, exclude_request_id=food_request.id):
        listing.status = ListingStatus.COLLECTED

    db.session.flush()
    record_audit_log(
        user_id=provider_profile.user_id,
        action="pickup_completed",
        resource_type="pickup_record",
        resource_id=pickup.id,
        description=(
            f"Pickup {pickup.id} completed; distribution record "
            f"{distribution.id} created."
        ),
    )
    create_notification(
        user_id=pickup.recipient.user_id,
        notification_type="pickup_completed",
        title="Pickup completed",
        message=f"Your pickup of {listing.food_name!r} was marked complete. Thank you!",
        related_resource_type="pickup_record",
        related_resource_id=pickup.id,
    )
    db.session.commit()
    return pickup


def fail_pickup(*, pickup_id: int, provider_profile, data: dict) -> PickupRecord:
    """
    Provider marks a scheduled/confirmed pickup as failed (e.g. a
    no-show). The request reverts to ACCEPTED so a new pickup can be
    scheduled for it, rather than being stuck or silently dropped.
    """
    pickup = _require_pickup(pickup_id)

    if pickup.provider_id != provider_profile.id:
        raise PickupError(
            "You do not have permission to update this pickup.", "FORBIDDEN", 403
        )

    if pickup.status not in ACTIVE_PICKUP_STATUSES:
        raise PickupError(
            f"Only scheduled or confirmed pickups can be marked failed (current "
            f"status: {pickup.status.value}).",
            "INVALID_PICKUP_STATE",
            409,
        )

    pickup.status = PickupStatus.FAILED
    reason = data.get("reason")
    if reason:
        pickup.confirmation_info = reason

    pickup.request.status = RequestStatus.ACCEPTED

    record_audit_log(
        user_id=provider_profile.user_id,
        action="pickup_failed",
        resource_type="pickup_record",
        resource_id=pickup.id,
        description=f"Pickup {pickup.id} marked failed; request reverted to accepted.",
    )
    create_notification(
        user_id=pickup.recipient.user_id,
        notification_type="pickup_failed",
        title="Pickup marked as failed",
        message=f"Pickup {pickup.id} was marked failed by the provider. "
        "Your request is still accepted and a new pickup can be scheduled.",
        related_resource_type="pickup_record",
        related_resource_id=pickup.id,
    )
    db.session.commit()
    return pickup


def cancel_pickup(*, pickup_id: int, recipient_profile) -> PickupRecord:
    """
    Recipient cancels a pickup they can no longer make. Like a failed
    pickup, the request reverts to ACCEPTED rather than being lost.
    """
    pickup = _require_pickup(pickup_id)

    if pickup.recipient_id != recipient_profile.id:
        raise PickupError(
            "You do not have permission to cancel this pickup.", "FORBIDDEN", 403
        )

    if pickup.status not in ACTIVE_PICKUP_STATUSES:
        raise PickupError(
            f"Only scheduled or confirmed pickups can be cancelled (current "
            f"status: {pickup.status.value}).",
            "INVALID_PICKUP_STATE",
            409,
        )

    pickup.status = PickupStatus.CANCELLED
    pickup.request.status = RequestStatus.ACCEPTED

    record_audit_log(
        user_id=recipient_profile.user_id,
        action="pickup_cancelled",
        resource_type="pickup_record",
        resource_id=pickup.id,
        description=f"Pickup {pickup.id} cancelled by recipient; request reverted to accepted.",
    )
    create_notification(
        user_id=pickup.provider.user_id,
        notification_type="pickup_cancelled",
        title="Pickup cancelled",
        message=f"The recipient cancelled pickup {pickup.id}. "
        "The request is still accepted and a new pickup can be scheduled.",
        related_resource_type="pickup_record",
        related_resource_id=pickup.id,
    )
    db.session.commit()
    return pickup


def get_pickup_for_viewer(*, pickup_id: int, current_user) -> PickupRecord:
    """Resource-level authorization: only the owning provider or the
    owning recipient may view a pickup record."""
    pickup = _require_pickup(pickup_id)

    is_owning_provider = (
        current_user.provider_profile is not None
        and pickup.provider_id == current_user.provider_profile.id
    )
    is_owning_recipient = (
        current_user.recipient_profile is not None
        and pickup.recipient_id == current_user.recipient_profile.id
    )

    if not (is_owning_provider or is_owning_recipient):
        raise PickupError(
            "You do not have permission to view this pickup record.", "FORBIDDEN", 403
        )
    return pickup


def list_pickups_query(*, current_user):
    """
    Base (unpaginated) query of pickups belonging to the current
    user, scoped by whichever profile(s) they have. Returns None if
    the user has neither a provider nor a recipient profile.
    """
    provider_profile = current_user.provider_profile
    recipient_profile = current_user.recipient_profile

    if provider_profile is None and recipient_profile is None:
        return None

    query = db.session.query(PickupRecord)
    if provider_profile is not None and recipient_profile is not None:
        query = query.filter(
            db.or_(
                PickupRecord.provider_id == provider_profile.id,
                PickupRecord.recipient_id == recipient_profile.id,
            )
        )
    elif provider_profile is not None:
        query = query.filter(PickupRecord.provider_id == provider_profile.id)
    else:
        query = query.filter(PickupRecord.recipient_id == recipient_profile.id)

    return query.order_by(PickupRecord.created_at.desc())
