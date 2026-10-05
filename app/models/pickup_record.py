"""
PickupRecord model — `pickup_records` table.

Tracks the physical handover of food for an accepted request. Kept
as its own table (separate from `FoodRequest`) because a request's
lifecycle (pending/accepted/rejected/...) is a different concern from
the pickup event itself (scheduled/confirmed/completed/failed), and
because the spec explicitly asks for pickup history to be preserved
even after a request is "completed" (section 16 — "Do not delete
completed pickup records").
"""

import enum

from app.extensions import db
from app.models.base import TimestampMixin


class PickupStatus(enum.Enum):
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PickupRecord(db.Model, TimestampMixin):
    __tablename__ = "pickup_records"

    id = db.Column(db.Integer, primary_key=True)

    request_id = db.Column(
        db.Integer,
        db.ForeignKey("food_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
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

    pickup_time = db.Column(db.DateTime(timezone=True), nullable=True)
    status = db.Column(
        db.Enum(PickupStatus, name="pickup_status"),
        nullable=False,
        default=PickupStatus.SCHEDULED,
        index=True,
    )

    # Free-text confirmation details — e.g. who signed for the pickup,
    # a confirmation code, or a note from the provider/recipient.
    confirmation_info = db.Column(db.Text, nullable=True)

    request = db.relationship("FoodRequest", back_populates="pickup_records")
    listing = db.relationship("FoodListing", back_populates="pickup_records")
    provider = db.relationship("ProviderProfile")
    recipient = db.relationship("RecipientProfile")
    distribution_record = db.relationship(
        "DistributionRecord", back_populates="pickup_record", uselist=False
    )

    def to_dict(self):
        res = {
            "id": self.id,
            "request_id": self.request_id,
            "listing_id": self.listing_id,
            "provider_id": self.provider_id,
            "recipient_id": self.recipient_id,
            "pickup_time": self.pickup_time.isoformat() if self.pickup_time else None,
            "status": self.status.value,
            "confirmation_info": self.confirmation_info,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if self.provider:
            res["provider"] = {
                "id": self.provider.id,
                "organization_name": self.provider.organization_name,
                "contact_info": self.provider.contact_info,
                "phone": getattr(self.provider, "phone", None) or self.provider.contact_info,
                "email": self.provider.user.email if self.provider.user else None,
                "address": self.provider.address,
                "city": self.provider.city,
                "state": self.provider.state,
                "latitude": float(self.provider.latitude) if self.provider.latitude is not None else None,
                "longitude": float(self.provider.longitude) if self.provider.longitude is not None else None,
            }
        if self.recipient:
            res["recipient"] = {
                "id": self.recipient.id,
                "organization_name": self.recipient.organization_name,
                "contact_info": self.recipient.contact_info,
                "phone": getattr(self.recipient, "phone", None) or self.recipient.contact_info,
                "email": self.recipient.user.email if self.recipient.user else None,
                "address": self.recipient.address,
                "city": self.recipient.city,
                "state": self.recipient.state,
                "latitude": float(self.recipient.latitude) if self.recipient.latitude is not None else None,
                "longitude": float(self.recipient.longitude) if self.recipient.longitude is not None else None,
            }
        if self.listing:
            res["listing"] = {
                "id": self.listing.id,
                "food_name": self.listing.food_name,
                "quantity": float(self.listing.quantity),
                "quantity_unit": self.listing.quantity_unit,
                "pickup_location": self.listing.pickup_location,
                "latitude": float(self.listing.latitude) if self.listing.latitude is not None else None,
                "longitude": float(self.listing.longitude) if self.listing.longitude is not None else None,
            }
        return res

    def __repr__(self):
        return f"<PickupRecord id={self.id} request_id={self.request_id} status={self.status}>"
