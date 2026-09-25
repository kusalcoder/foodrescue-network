"""
ProviderProfile model — `provider_profiles` table.

Represents the business/organization side of a Provider user account
(restaurant, event organizer, or other food-donating organization).
Linked one-to-one with a `User` row that has role = PROVIDER.
"""

import enum

from app.extensions import db
from app.models.base import TimestampMixin


class ProfileStatus(enum.Enum):
    """Administrative status of the profile itself (separate from the
    underlying User's account status)."""

    ACTIVE = "active"
    INACTIVE = "inactive"


class ProviderProfile(db.Model, TimestampMixin):
    __tablename__ = "provider_profiles"

    id = db.Column(db.Integer, primary_key=True)

    # One provider profile belongs to exactly one user. unique=True
    # enforces the one-to-one relationship at the database level.
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

    # Latitude/longitude are optional ("where available", per spec)
    # since not every provider will supply precise coordinates.
    # Precision: Numeric(9,6) comfortably covers standard GPS precision.
    latitude = db.Column(db.Numeric(9, 6), nullable=True)
    longitude = db.Column(db.Numeric(9, 6), nullable=True)

    description = db.Column(db.Text, nullable=True)

    status = db.Column(
        db.Enum(ProfileStatus, name="provider_profile_status"),
        nullable=False,
        default=ProfileStatus.ACTIVE,
    )

    user = db.relationship("User", back_populates="provider_profile")
    listings = db.relationship(
        "FoodListing", back_populates="provider", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # Basic sanity constraints on coordinates (full validation
        # also happens in the application layer — this is a safety
        # net at the database level).
        db.CheckConstraint(
            "latitude IS NULL OR (latitude >= -90 AND latitude <= 90)",
            name="ck_provider_latitude_range",
        ),
        db.CheckConstraint(
            "longitude IS NULL OR (longitude >= -180 AND longitude <= 180)",
            name="ck_provider_longitude_range",
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
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<ProviderProfile id={self.id} organization_name={self.organization_name!r}>"
