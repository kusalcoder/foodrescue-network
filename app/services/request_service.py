"""
Food request workflow business logic (spec sections 13-15, 34-36).

Request lifecycle handled in this phase: PENDING -> ACCEPTED / REJECTED
/ CANCELLED. The further PICKUP_PENDING -> COMPLETED steps belong to
Phase 7 (Pickup and Distribution) and are not reachable yet.

Quantity safety (spec sections 15 & 35) works like this:
    - A listing's original `quantity` never changes.
    - "Remaining" quantity is always computed on demand as:
          listing.quantity - SUM(requested_quantity of that listing's
                                  ACCEPTED requests)
    - Submitting a request only does a soft/advisory check against
      remaining — multiple recipients may have overlapping PENDING
      requests at once (spec section 15's own example relies on this:
      "Recipient B can potentially request from the remaining
      quantity" while A's request is still pending).
    - The HARD guarantee is enforced at ACCEPT time, inside a
      transaction that takes a row lock on the FoodListing
      (`SELECT ... FOR UPDATE`), so two concurrent "accept" calls for
      the same listing can never both succeed if doing so would
      exceed the listing's quantity — this is the concrete
      demonstration of spec section 35's concurrency requirement.
"""

from app.extensions import db
from app.models import FoodListing, FoodRequest, ListingStatus, RequestStatus
from app.models.base import utcnow
from app.services.notification_service import create_notification
from app.utils.audit import record_audit_log
from app.utils.validation import validate_positive_number


class RequestError(Exception):
    def __init__(self, message: str, error_code: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code


def _accepted_quantity_for_listing(listing_id: int, exclude_request_id: int = None):
    """Sum of requested_quantity across ACCEPTED requests for a listing."""
    query = db.session.query(
        db.func.coalesce(db.func.sum(FoodRequest.requested_quantity), 0)
    ).filter(
        FoodRequest.listing_id == listing_id,
        FoodRequest.status == RequestStatus.ACCEPTED,
    )
    if exclude_request_id is not None:
        query = query.filter(FoodRequest.id != exclude_request_id)
    return query.scalar() or 0


def create_request(*, recipient_profile, data: dict) -> FoodRequest:
    """Recipient submits a request to collect from a listing."""
    if recipient_profile.verification_status.value != "verified":
        raise RequestError(
            "Your recipient organization must be verified before requesting food.",
            "RECIPIENT_NOT_VERIFIED",
            403,
        )

    listing_id = data.get("listing_id")
    listing = db.session.get(FoodListing, listing_id) if listing_id else None
    if listing is None:
        raise RequestError("Listing not found.", "LISTING_NOT_FOUND", 404)

    if listing.status != ListingStatus.AVAILABLE:
        raise RequestError(
            f"This listing is not available for requests (status: {listing.status.value}).",
            "LISTING_NOT_AVAILABLE",
            409,
        )

    if listing.pickup_end_time <= utcnow():
        raise RequestError(
            "This listing's pickup window has already ended.",
            "LISTING_EXPIRED",
            409,
        )

    requested_quantity = data.get("requested_quantity")
    qty_error = validate_positive_number(requested_quantity, "Requested quantity")
    if qty_error:
        raise RequestError(qty_error, "VALIDATION_ERROR", 422)

    remaining = float(listing.quantity) - float(
        _accepted_quantity_for_listing(listing.id)
    )
    if float(requested_quantity) > remaining:
        raise RequestError(
            f"Requested quantity exceeds what's still available ({remaining} {listing.quantity_unit} remaining).",
            "QUANTITY_EXCEEDS_AVAILABLE",
            409,
        )

    duplicate = (
        db.session.query(FoodRequest)
        .filter(
            FoodRequest.listing_id == listing.id,
            FoodRequest.recipient_id == recipient_profile.id,
            FoodRequest.status.in_([RequestStatus.PENDING, RequestStatus.ACCEPTED]),
        )
        .first()
    )
    if duplicate is not None:
        raise RequestError(
            "You already have an active request for this listing.",
            "DUPLICATE_REQUEST",
            409,
        )

    request = FoodRequest(
        listing_id=listing.id,
        recipient_id=recipient_profile.id,
        requested_quantity=requested_quantity,
        request_message=data.get("request_message"),
        status=RequestStatus.PENDING,
    )
    db.session.add(request)
    db.session.flush()

    record_audit_log(
        user_id=recipient_profile.user_id,
        action="request_created",
        resource_type="food_request",
        resource_id=request.id,
        description=f"Request for {requested_quantity} {listing.quantity_unit} of listing {listing.id}.",
    )
    create_notification(
        user_id=listing.provider.user_id,
        notification_type="request_received",
        title="New request for your listing",
        message=f"A recipient requested {requested_quantity} {listing.quantity_unit} "
        f"of {listing.food_name!r}.",
        related_resource_type="food_request",
        related_resource_id=request.id,
    )
    db.session.commit()
    return request


def _require_request(request_id: int) -> FoodRequest:
    request = db.session.get(FoodRequest, request_id)
    if request is None:
        raise RequestError("Request not found.", "REQUEST_NOT_FOUND", 404)
    return request


def accept_request(*, request_id: int, provider_profile) -> FoodRequest:
    """
    Provider accepts a pending request.

    The quantity check and status update happen together, inside a
    transaction, against a ROW-LOCKED copy of the listing
    (`with_for_update()`). If two requests for the same listing are
    accepted at nearly the same instant, PostgreSQL forces the second
    transaction to wait for the first to finish before it can even
    read the listing's current state — so the second one always sees
    the first one's effect and can correctly reject if there's no
    longer enough quantity left.
    """
    request = _require_request(request_id)

    # Lock the listing row FIRST, before checking anything — this is
    # what makes the whole check-then-update sequence atomic with
    # respect to other concurrent accept attempts on the same listing.
    listing = (
        db.session.query(FoodListing)
        .filter_by(id=request.listing_id)
        .with_for_update()
        .one()
    )

    if listing.provider_id != provider_profile.id:
        db.session.rollback()
        raise RequestError(
            "You do not have permission to manage this request.", "FORBIDDEN", 403
        )

    if request.status != RequestStatus.PENDING:
        db.session.rollback()
        raise RequestError(
            f"Only pending requests can be accepted (current status: {request.status.value}).",
            "INVALID_REQUEST_STATE",
            409,
        )

    remaining = float(listing.quantity) - float(
        _accepted_quantity_for_listing(listing.id)
    )
    if float(request.requested_quantity) > remaining:
        db.session.rollback()
        raise RequestError(
            f"Cannot accept: only {remaining} {listing.quantity_unit} remain, "
            f"but this request asks for {float(request.requested_quantity)}.",
            "QUANTITY_EXCEEDS_AVAILABLE",
            409,
        )

    request.status = RequestStatus.ACCEPTED

    new_remaining = remaining - float(request.requested_quantity)
    if new_remaining <= 0:
        listing.status = ListingStatus.RESERVED

    record_audit_log(
        user_id=provider_profile.user_id,
        action="request_accepted",
        resource_type="food_request",
        resource_id=request.id,
        description=f"Request {request.id} accepted.",
    )
    create_notification(
        user_id=request.recipient.user_id,
        notification_type="request_accepted",
        title="Your request was accepted",
        message=f"Your request for {listing.food_name!r} was accepted by the provider.",
        related_resource_type="food_request",
        related_resource_id=request.id,
    )
    db.session.commit()
    return request


def reject_request(*, request_id: int, provider_profile) -> FoodRequest:
    request = _require_request(request_id)

    if request.listing.provider_id != provider_profile.id:
        raise RequestError(
            "You do not have permission to manage this request.", "FORBIDDEN", 403
        )

    if request.status != RequestStatus.PENDING:
        raise RequestError(
            f"Only pending requests can be rejected (current status: {request.status.value}).",
            "INVALID_REQUEST_STATE",
            409,
        )

    request.status = RequestStatus.REJECTED

    record_audit_log(
        user_id=provider_profile.user_id,
        action="request_rejected",
        resource_type="food_request",
        resource_id=request.id,
        description=f"Request {request.id} rejected.",
    )
    create_notification(
        user_id=request.recipient.user_id,
        notification_type="request_rejected",
        title="Your request was rejected",
        message=f"Your request for {request.listing.food_name!r} was rejected by the provider.",
        related_resource_type="food_request",
        related_resource_id=request.id,
    )
    db.session.commit()
    return request


def cancel_request(*, request_id: int, recipient_profile) -> FoodRequest:
    """
    Recipient cancels their own request. Allowed while PENDING or
    ACCEPTED (cancelling an accepted-but-not-yet-picked-up request
    correctly frees the quantity it was holding — handled here under
    the same row-lock discipline as accept_request, since it changes
    the same shared quantity).
    """
    request = _require_request(request_id)

    if request.recipient_id != recipient_profile.id:
        raise RequestError(
            "You do not have permission to manage this request.", "FORBIDDEN", 403
        )

    if request.status not in (RequestStatus.PENDING, RequestStatus.ACCEPTED):
        raise RequestError(
            f"Only pending or accepted requests can be cancelled (current status: {request.status.value}).",
            "INVALID_REQUEST_STATE",
            409,
        )

    was_accepted = request.status == RequestStatus.ACCEPTED

    if was_accepted:
        listing = (
            db.session.query(FoodListing)
            .filter_by(id=request.listing_id)
            .with_for_update()
            .one()
        )
    request.status = RequestStatus.CANCELLED

    if was_accepted and listing.status == ListingStatus.RESERVED:
        # Cancelling an accepted request frees up quantity, so a fully
        # reserved listing becomes available again.
        listing.status = ListingStatus.AVAILABLE

    record_audit_log(
        user_id=recipient_profile.user_id,
        action="request_cancelled",
        resource_type="food_request",
        resource_id=request.id,
        description=f"Request {request.id} cancelled by recipient.",
    )
    create_notification(
        user_id=request.listing.provider.user_id,
        notification_type="request_cancelled",
        title="A request was cancelled",
        message=f"The recipient cancelled their request for {request.listing.food_name!r}.",
        related_resource_type="food_request",
        related_resource_id=request.id,
    )
    db.session.commit()
    return request


def get_request_for_viewer(*, request_id: int, current_user) -> FoodRequest:
    """
    Resource-level authorization for GET /api/requests/<id>: only the
    requesting recipient or the owning provider may view a request.
    """
    request = _require_request(request_id)

    is_owning_recipient = (
        current_user.recipient_profile is not None
        and request.recipient_id == current_user.recipient_profile.id
    )
    is_owning_provider = (
        current_user.provider_profile is not None
        and request.listing.provider_id == current_user.provider_profile.id
    )

    if not (is_owning_recipient or is_owning_provider):
        raise RequestError(
            "You do not have permission to view this request.", "FORBIDDEN", 403
        )
    return request


def list_requests_for_recipient(*, recipient_profile):
    return (
        db.session.query(FoodRequest)
        .filter_by(recipient_id=recipient_profile.id)
        .order_by(FoodRequest.created_at.desc())
        .all()
    )


def list_requests_for_listing(*, listing_id: int, provider_profile):
    listing = db.session.get(FoodListing, listing_id)
    if listing is None:
        raise RequestError("Listing not found.", "LISTING_NOT_FOUND", 404)
    if listing.provider_id != provider_profile.id:
        raise RequestError(
            "You do not have permission to view requests for this listing.",
            "FORBIDDEN",
            403,
        )
    return (
        db.session.query(FoodRequest)
        .filter_by(listing_id=listing_id)
        .order_by(FoodRequest.created_at.desc())
        .all()
    )
