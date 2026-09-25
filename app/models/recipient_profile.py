"""
RecipientProfile model — `recipient_profiles` table.

Represents a recipient organization (e.g. a shelter, community
kitchen, or NGO) that can request surplus food. Linked one-to-one
with a `User` row that has role = RECIPIENT.

Recipients have a `verification_status` in addition to a general
active/inactive status, because the spec requires that "Only
authorized recipient organizations should be able to request food
listings" — an admin needs a way to mark an org as verified before
it's allowed to place requests. That authorization check itself is
implemented in Phase 6 (Request Workflow); this model just stores
the flag it depends on.
"""

import enum

from app.extensions import db
from app.models.base import TimestampMixin


class VerificationStatus(enum.Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


class RecipientProfile(db.Model, TimestampMixin):
    __tablename__ = "recipient_profiles"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    organization_name = db.Column(db.String(200), nullable=False)
    contact_info = db.Column(db.String(255), nullable=True)

    address = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(100), nullable=True, index=True)

    latitude = db.Column(db.Numeric(9, 6), nullable=True)
    longitude = db.Column(db.Numeric(9, 6), nullable=True)

    description = db.Column(db.Text, nullable=True)

    verification_status = db.Column(
        db.Enum(VerificationStatus, name="recipient_verification_status"),
        nullable=False,
        default=VerificationStatus.PENDING,
    )

    user = db.relationship("User", back_populates="recipient_profile")
    requests = db.relationship(
        "FoodRequest", back_populates="recipient", cascade="all, delete-orphan"
    )

    __table_args__ = (
        db.CheckConstraint(
            "latitude IS NULL OR (latitude >= -90 AND latitude <= 90)",
            name="ck_recipient_latitude_range",
        ),
        db.CheckConstraint(
            "longitude IS NULL OR (longitude >= -180 AND longitude <= 180)",
            name="ck_recipient_longitude_range",
        ),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "organization_name": self.organization_name,
            "contact_info": self.contact_info,
            "address": self.address,
            "city": self.city,
            "latitude": float(self.latitude) if self.latitude is not None else None,
            "longitude": float(self.longitude) if self.longitude is not None else None,
            "description": self.description,
            "verification_status": self.verification_status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<RecipientProfile id={self.id} organization_name={self.organization_name!r}>"
