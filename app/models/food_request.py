"""
FoodRequest model — `food_requests` table.

A recipient organization's request to collect (some or all of) the
quantity offered in a `FoodListing`. The accept/reject/cancel workflow
and the quantity-safety rules (spec sections 13–15, 35) are enforced
in the service layer in Phase 6 — this model just defines the shape
of the data and the set of valid status values.
"""

import enum

from app.extensions import db
from app.models.base import TimestampMixin


class RequestStatus(enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    PICKUP_PENDING = "pickup_pending"
    COMPLETED = "completed"


class FoodRequest(db.Model, TimestampMixin):
    __tablename__ = "food_requests"

    id = db.Column(db.Integer, primary_key=True)

    listing_id = db.Column(
        db.Integer,
        db.ForeignKey("food_listings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recipient_id = db.Column(
        db.Integer,
        db.ForeignKey("recipient_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    requested_quantity = db.Column(db.Numeric(10, 2), nullable=False)
    request_message = db.Column(db.Text, nullable=True)

    status = db.Column(
        db.Enum(RequestStatus, name="request_status"),
        nullable=False,
        default=RequestStatus.PENDING,
        index=True,
    )

    # "requested_timestamp" from the spec — reusing the TimestampMixin's
    # created_at for this, since a request's creation time IS the
    # moment it was requested. updated_at (also from the mixin) tracks
    # the most recent status change.

    listing = db.relationship("FoodListing", back_populates="requests")
    recipient = db.relationship("RecipientProfile", back_populates="requests")
    pickup_records = db.relationship("PickupRecord", back_populates="request")

    __table_args__ = (
        db.CheckConstraint(
            "requested_quantity > 0", name="ck_request_quantity_positive"
        ),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "listing_id": self.listing_id,
            "recipient_id": self.recipient_id,
            "requested_quantity": float(self.requested_quantity),
            "request_message": self.request_message,
            "status": self.status.value,
            "requested_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<FoodRequest id={self.id} listing_id={self.listing_id} status={self.status}>"
