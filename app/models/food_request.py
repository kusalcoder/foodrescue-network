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
        res = {
            "id": self.id,
            "listing_id": self.listing_id,
            "recipient_id": self.recipient_id,
            "requested_quantity": float(self.requested_quantity),
            "request_message": self.request_message,
            "status": self.status.value,
            "requested_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
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
                "verification_status": self.recipient.verification_status.value if hasattr(self.recipient.verification_status, "value") else str(self.recipient.verification_status),
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
                "provider_id": self.listing.provider_id,
                "provider_name": self.listing.provider.organization_name if self.listing.provider else None,
                "provider_contact": self.listing.provider.contact_info if self.listing.provider else None,
                "provider_phone": getattr(self.listing.provider, "phone", None) or (self.listing.provider.contact_info if self.listing.provider else None),
                "provider_email": self.listing.provider.user.email if (self.listing.provider and self.listing.provider.user) else None,
                "provider_state": self.listing.provider.state if self.listing.provider else None,
            }
        return res

    def __repr__(self):
        return f"<FoodRequest id={self.id} listing_id={self.listing_id} status={self.status}>"
