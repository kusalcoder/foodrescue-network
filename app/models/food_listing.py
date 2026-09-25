"""
FoodListing model — `food_listings` table.

A surplus-food listing published by a Provider. This is the central
entity of the whole platform — recipients search, filter, and request
against these rows.

Important domain note (spec section 46): `conditions` stores
information *supplied by the provider* (e.g. "keep refrigerated").
The system never transforms this into a safety guarantee — that's an
application-layer rule enforced in the routes/services, not something
the model can express, but it's called out here so future contributors
don't "helpfully" add a food-safety score column.
"""

import enum

from app.extensions import db
from app.models.base import TimestampMixin


class FoodCategory(enum.Enum):
    PREPARED_FOOD = "prepared_food"
    PACKAGED_FOOD = "packaged_food"
    BAKERY = "bakery"
    FRUITS = "fruits"
    VEGETABLES = "vegetables"
    OTHER = "other"


class ListingStatus(enum.Enum):
    """
    Lifecycle states from spec section 8 / section 12.

    Valid transitions are enforced in the service layer (Phase 6),
    not here — the database only guarantees the value is one of
    these six options.
    """

    AVAILABLE = "available"
    RESERVED = "reserved"
    PICKUP_PENDING = "pickup_pending"
    COLLECTED = "collected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class FoodListing(db.Model, TimestampMixin):
    __tablename__ = "food_listings"

    id = db.Column(db.Integer, primary_key=True)

    provider_id = db.Column(
        db.Integer,
        db.ForeignKey("provider_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    food_name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)

    category = db.Column(
        db.Enum(FoodCategory, name="food_category"),
        nullable=False,
        index=True,
    )

    # Quantity is split into a numeric amount + a free-text unit
    # ("meals", "kg", "boxes", "packets" — spec section 10) so we can
    # validate positivity without hardcoding a fixed unit list.
    quantity = db.Column(db.Numeric(10, 2), nullable=False)
    quantity_unit = db.Column(db.String(50), nullable=False)

    available_date = db.Column(db.Date, nullable=False)
    pickup_start_time = db.Column(db.DateTime(timezone=True), nullable=False)
    pickup_end_time = db.Column(db.DateTime(timezone=True), nullable=False)

    pickup_location = db.Column(db.String(255), nullable=False)
    latitude = db.Column(db.Numeric(9, 6), nullable=True)
    longitude = db.Column(db.Numeric(9, 6), nullable=True)

    # Provider-supplied notes such as "pickup only", "keep refrigerated".
    # Stored as-is; never algorithmically reinterpreted as a safety claim.
    conditions = db.Column(db.Text, nullable=True)

    status = db.Column(
        db.Enum(ListingStatus, name="listing_status"),
        nullable=False,
        default=ListingStatus.AVAILABLE,
        index=True,
    )

    provider = db.relationship("ProviderProfile", back_populates="listings")
    requests = db.relationship(
        "FoodRequest", back_populates="listing", cascade="all, delete-orphan"
    )
    pickup_records = db.relationship("PickupRecord", back_populates="listing")
    distribution_records = db.relationship(
        "DistributionRecord", back_populates="listing"
    )

    __table_args__ = (
        db.CheckConstraint("quantity > 0", name="ck_listing_quantity_positive"),
        db.CheckConstraint(
            "pickup_end_time > pickup_start_time",
            name="ck_listing_pickup_window_valid",
        ),
        db.CheckConstraint(
            "latitude IS NULL OR (latitude >= -90 AND latitude <= 90)",
            name="ck_listing_latitude_range",
        ),
        db.CheckConstraint(
            "longitude IS NULL OR (longitude >= -180 AND longitude <= 180)",
            name="ck_listing_longitude_range",
        ),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "provider_id": self.provider_id,
            "food_name": self.food_name,
            "description": self.description,
            "category": self.category.value,
            "quantity": float(self.quantity),
            "quantity_unit": self.quantity_unit,
            "available_date": self.available_date.isoformat()
            if self.available_date
            else None,
            "pickup_start_time": self.pickup_start_time.isoformat()
            if self.pickup_start_time
            else None,
            "pickup_end_time": self.pickup_end_time.isoformat()
            if self.pickup_end_time
            else None,
            "pickup_location": self.pickup_location,
            "latitude": float(self.latitude) if self.latitude is not None else None,
            "longitude": float(self.longitude) if self.longitude is not None else None,
            "conditions": self.conditions,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<FoodListing id={self.id} food_name={self.food_name!r} status={self.status}>"
