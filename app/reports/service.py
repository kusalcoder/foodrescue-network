"""
Read-only reporting/aggregation logic — Phase 10.

Every function here summarizes rows that already exist
(`DistributionRecord`, `FoodRequest`, `PickupRecord`, `FoodListing`)
rather than creating or changing anything — same "read-only history"
spirit as Phase 7's distribution endpoints. Nothing in this module
calls `db.session.commit()`.

Role-based scoping (who is allowed to see whose numbers) is enforced
by the route layer, not here — these functions take whatever
`provider_id`/`recipient_id` filters they're given at face value. See
app/routes/reports.py for the actual access rules.
"""

from datetime import date

from app.extensions import db
from app.models import (
    DistributionRecord,
    FoodListing,
    FoodRequest,
    PickupRecord,
    ProviderProfile,
    RecipientProfile,
    User,
)


class ReportError(Exception):
    def __init__(self, message: str, error_code: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code


def parse_optional_date(value, field_name: str):
    """
    Unlike listing_service's _parse_date, a report's start_date/
    end_date are both OPTIONAL — an absent value just means "no lower/
    upper bound" rather than a validation error. Only a present-but-
    malformed value is an error.
    """
    if value is None or value == "":
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ReportError(
            f"{field_name} must be a valid ISO-8601 date (YYYY-MM-DD).",
            "VALIDATION_ERROR",
            422,
        )


def _apply_distribution_filters(
    query, *, provider_id=None, recipient_id=None, start_date=None, end_date=None
):
    if provider_id is not None:
        query = query.filter(DistributionRecord.provider_id == provider_id)
    if recipient_id is not None:
        query = query.filter(DistributionRecord.recipient_id == recipient_id)
    if start_date is not None:
        query = query.filter(
            db.func.date(DistributionRecord.pickup_datetime) >= start_date
        )
    if end_date is not None:
        query = query.filter(
            db.func.date(DistributionRecord.pickup_datetime) <= end_date
        )
    return query


def distribution_summary(
    *, provider_id=None, recipient_id=None, start_date=None, end_date=None
):
    """
    Headline numbers for a set of distribution records: how many,
    how much food (total quantity), and how many distinct
    providers/recipients were involved — optionally scoped to one
    provider, one recipient, and/or a date range (inclusive, by
    pickup date).
    """
    if start_date is not None and end_date is not None and start_date > end_date:
        raise ReportError(
            "start_date must not be after end_date.", "VALIDATION_ERROR", 422
        )

    base = _apply_distribution_filters(
        db.session.query(DistributionRecord),
        provider_id=provider_id,
        recipient_id=recipient_id,
        start_date=start_date,
        end_date=end_date,
    )

    totals = base.with_entities(
        db.func.count(DistributionRecord.id),
        db.func.coalesce(db.func.sum(DistributionRecord.quantity), 0),
        db.func.count(db.func.distinct(DistributionRecord.provider_id)),
        db.func.count(db.func.distinct(DistributionRecord.recipient_id)),
    ).one()

    total_distributions, total_quantity, unique_providers, unique_recipients = totals

    return {
        "total_distributions": total_distributions,
        "total_quantity": float(total_quantity),
        "unique_providers": unique_providers,
        "unique_recipients": unique_recipients,
        "filters": {
            "provider_id": provider_id,
            "recipient_id": recipient_id,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
        },
    }


def distribution_by_category(
    *, provider_id=None, recipient_id=None, start_date=None, end_date=None
):
    """
    Same scope/filters as distribution_summary, but broken down by
    `food_category` (the category as it stood at completion time —
    see DistributionRecord's own docstring on why that's
    denormalized), ordered by total quantity descending.
    """
    if start_date is not None and end_date is not None and start_date > end_date:
        raise ReportError(
            "start_date must not be after end_date.", "VALIDATION_ERROR", 422
        )

    base = _apply_distribution_filters(
        db.session.query(
            DistributionRecord.food_category,
            db.func.count(DistributionRecord.id),
            db.func.coalesce(db.func.sum(DistributionRecord.quantity), 0),
        ),
        provider_id=provider_id,
        recipient_id=recipient_id,
        start_date=start_date,
        end_date=end_date,
    )

    rows = (
        base.group_by(DistributionRecord.food_category)
        .order_by(db.func.sum(DistributionRecord.quantity).desc())
        .all()
    )

    return [
        {
            "category": category or "uncategorized",
            "distributions": count,
            "total_quantity": float(quantity),
        }
        for category, count, quantity in rows
    ]


def provider_activity_summary(*, provider_profile: ProviderProfile) -> dict:
    """
    One provider's own activity across every phase built so far:
    listings by status, requests received/accepted/rejected, pickups
    by outcome, and total quantity actually redistributed.
    """
    listings_by_status = dict(
        db.session.query(FoodListing.status, db.func.count(FoodListing.id))
        .filter(FoodListing.provider_id == provider_profile.id)
        .group_by(FoodListing.status)
        .all()
    )

    requests_by_status = dict(
        db.session.query(FoodRequest.status, db.func.count(FoodRequest.id))
        .join(FoodListing, FoodRequest.listing_id == FoodListing.id)
        .filter(FoodListing.provider_id == provider_profile.id)
        .group_by(FoodRequest.status)
        .all()
    )

    pickups_by_status = dict(
        db.session.query(PickupRecord.status, db.func.count(PickupRecord.id))
        .filter(PickupRecord.provider_id == provider_profile.id)
        .group_by(PickupRecord.status)
        .all()
    )

    total_quantity_distributed = (
        db.session.query(db.func.coalesce(db.func.sum(DistributionRecord.quantity), 0))
        .filter(DistributionRecord.provider_id == provider_profile.id)
        .scalar()
    )

    return {
        "listings_by_status": {
            status.value: count for status, count in listings_by_status.items()
        },
        "requests_by_status": {
            status.value: count for status, count in requests_by_status.items()
        },
        "pickups_by_status": {
            status.value: count for status, count in pickups_by_status.items()
        },
        "total_quantity_distributed": float(total_quantity_distributed),
    }


def recipient_activity_summary(*, recipient_profile: RecipientProfile) -> dict:
    """
    One recipient's own activity: requests by status, pickups by
    outcome, and total quantity actually received.
    """
    requests_by_status = dict(
        db.session.query(FoodRequest.status, db.func.count(FoodRequest.id))
        .filter(FoodRequest.recipient_id == recipient_profile.id)
        .group_by(FoodRequest.status)
        .all()
    )

    pickups_by_status = dict(
        db.session.query(PickupRecord.status, db.func.count(PickupRecord.id))
        .filter(PickupRecord.recipient_id == recipient_profile.id)
        .group_by(PickupRecord.status)
        .all()
    )

    total_quantity_received = (
        db.session.query(db.func.coalesce(db.func.sum(DistributionRecord.quantity), 0))
        .filter(DistributionRecord.recipient_id == recipient_profile.id)
        .scalar()
    )

    return {
        "requests_by_status": {
            status.value: count for status, count in requests_by_status.items()
        },
        "pickups_by_status": {
            status.value: count for status, count in pickups_by_status.items()
        },
        "total_quantity_received": float(total_quantity_received),
    }


def platform_summary() -> dict:
    """
    Admin-only, platform-wide snapshot: users by role, listings by
    status, recipients by verification status, and all-time
    distribution totals. Not date-scoped — for a time-ranged view,
    use distribution_summary()/distribution_by_category() instead.
    """
    users_by_role = dict(
        db.session.query(User.role, db.func.count(User.id)).group_by(User.role).all()
    )

    listings_by_status = dict(
        db.session.query(FoodListing.status, db.func.count(FoodListing.id))
        .group_by(FoodListing.status)
        .all()
    )

    recipients_by_verification = dict(
        db.session.query(
            RecipientProfile.verification_status, db.func.count(RecipientProfile.id)
        )
        .group_by(RecipientProfile.verification_status)
        .all()
    )

    total_distributions, total_quantity = db.session.query(
        db.func.count(DistributionRecord.id),
        db.func.coalesce(db.func.sum(DistributionRecord.quantity), 0),
    ).one()

    return {
        "users_by_role": {role.value: count for role, count in users_by_role.items()},
        "listings_by_status": {
            status.value: count for status, count in listings_by_status.items()
        },
        "recipients_by_verification": {
            status.value: count for status, count in recipients_by_verification.items()
        },
        "total_distributions": total_distributions,
        "total_quantity_distributed": float(total_quantity),
    }
