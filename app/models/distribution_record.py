"""
DistributionRecord model — `distribution_records` table.

The permanent historical record of a completed redistribution,
created once a pickup is completed. Kept deliberately simple and
append-only (spec section 17 / rule #6 — "Completed distributions
cannot be arbitrarily changed") — this table is written to once by
the service layer in Phase 7 and after that treated as read-only
history for provider/recipient/admin reports.
"""

from app.extensions import db
from app.models.base import utcnow


class DistributionRecord(db.Model):
    __tablename__ = "distribution_records"

    id = db.Column(db.Integer, primary_key=True)

    listing_id = db.Column(
        db.Integer,
        db.ForeignKey("food_listings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_id = db.Column(
        db.Integer,
        db.ForeignKey("provider_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recipient_id = db.Column(
        db.Integer,
        db.ForeignKey("recipient_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pickup_record_id = db.Column(
        db.Integer,
        db.ForeignKey("pickup_records.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )

    quantity = db.Column(db.Numeric(10, 2), nullable=False)
    pickup_datetime = db.Column(db.DateTime(timezone=True), nullable=True)

    # Denormalized copy of the listing's category at completion time.
    # Kept intentionally redundant so historical reports remain
    # accurate even if a listing's category metadata changes later.
    food_category = db.Column(db.String(50), nullable=True)

    completion_status = db.Column(db.String(50), nullable=False, default="completed")

    # Distribution records are historical/append-only, so only a
    # created_at is needed — there is deliberately no updated_at
    # (see module docstring: these rows should not be edited).
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    listing = db.relationship("FoodListing", back_populates="distribution_records")
    provider = db.relationship("ProviderProfile")
    recipient = db.relationship("RecipientProfile")
    pickup_record = db.relationship(
        "PickupRecord", back_populates="distribution_record"
    )

    __table_args__ = (
        db.CheckConstraint("quantity > 0", name="ck_distribution_quantity_positive"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "listing_id": self.listing_id,
            "provider_id": self.provider_id,
            "recipient_id": self.recipient_id,
            "pickup_record_id": self.pickup_record_id,
            "quantity": float(self.quantity),
            "pickup_datetime": self.pickup_datetime.isoformat()
            if self.pickup_datetime
            else None,
            "food_category": self.food_category,
            "completion_status": self.completion_status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<DistributionRecord id={self.id} listing_id={self.listing_id}>"
