"""
Shared model utilities.

`TimestampMixin` adds `created_at` / `updated_at` columns to any model
that inherits it, so we don't repeat this on every table. Almost
every table in the spec (users, listings, requests, pickups, etc.)
needs both columns.
"""

from datetime import datetime, timezone

from app.extensions import db


def utcnow():
    """Timezone-aware UTC timestamp helper, used as a column default.

    Using a function (instead of `datetime.utcnow()` directly) means
    the timestamp is computed at insert time, not at class-definition
    time.
    """
    return datetime.now(timezone.utc)


class TimestampMixin:
    """Adds created_at/updated_at columns to a model."""

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )
