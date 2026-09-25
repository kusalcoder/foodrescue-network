"""
Distribution history — read-only access to `DistributionRecord` rows.

There is deliberately no create/update/delete here: every
`DistributionRecord` is written exactly once, inside
`pickup_service.complete_pickup`, as part of that same transaction
(spec section 17 / rule #6 — completed distributions are permanent).
This module only answers "what has this provider/recipient actually
distributed or received so far", for history views and (in a later
phase) reporting.
"""

from app.extensions import db
from app.models import DistributionRecord


class DistributionError(Exception):
    def __init__(self, message: str, error_code: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code


def _require_distribution(distribution_id: int) -> DistributionRecord:
    record = db.session.get(DistributionRecord, distribution_id)
    if record is None:
        raise DistributionError(
            "Distribution record not found.", "DISTRIBUTION_NOT_FOUND", 404
        )
    return record


def get_distribution_for_viewer(
    *, distribution_id: int, current_user
) -> DistributionRecord:
    """Resource-level authorization: only the provider who gave the
    food or the recipient who received it may view this record."""
    record = _require_distribution(distribution_id)

    is_owning_provider = (
        current_user.provider_profile is not None
        and record.provider_id == current_user.provider_profile.id
    )
    is_owning_recipient = (
        current_user.recipient_profile is not None
        and record.recipient_id == current_user.recipient_profile.id
    )

    if not (is_owning_provider or is_owning_recipient):
        raise DistributionError(
            "You do not have permission to view this distribution record.",
            "FORBIDDEN",
            403,
        )
    return record


def list_distributions_query(*, current_user):
    """
    Base (unpaginated) query of distribution history belonging to the
    current user, scoped by whichever profile(s) they have. Returns
    None if the user has neither a provider nor a recipient profile.
    """
    provider_profile = current_user.provider_profile
    recipient_profile = current_user.recipient_profile

    if provider_profile is None and recipient_profile is None:
        return None

    query = db.session.query(DistributionRecord)
    if provider_profile is not None and recipient_profile is not None:
        query = query.filter(
            db.or_(
                DistributionRecord.provider_id == provider_profile.id,
                DistributionRecord.recipient_id == recipient_profile.id,
            )
        )
    elif provider_profile is not None:
        query = query.filter(DistributionRecord.provider_id == provider_profile.id)
    else:
        query = query.filter(
            DistributionRecord.recipient_id == recipient_profile.id
        )

    return query.order_by(DistributionRecord.created_at.desc())
