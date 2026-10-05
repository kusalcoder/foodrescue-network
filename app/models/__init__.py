"""
Importing every model here ensures they are all registered with
SQLAlchemy's metadata as soon as `app.models` is imported anywhere.

This matters for Flask-Migrate: when it autogenerates a migration
(`flask db migrate`), it inspects `db.metadata` to see what tables
*should* exist. If a model module was never imported, its table
would be invisible to that inspection and get silently dropped from
the generated migration.
"""

from app.models.user import User, UserRole, AccountStatus
from app.models.provider_profile import ProviderProfile, ProfileStatus
from app.models.recipient_profile import RecipientProfile, VerificationStatus
from app.models.food_listing import FoodListing, FoodCategory, ListingStatus
from app.models.food_request import FoodRequest, RequestStatus
from app.models.pickup_record import PickupRecord, PickupStatus
from app.models.distribution_record import DistributionRecord
from app.models.notification import Notification
from app.models.audit_log import AuditLog
from app.models.token_blocklist import TokenBlocklist

__all__ = [
    "User",
    "UserRole",
    "AccountStatus",
    "ProviderProfile",
    "ProfileStatus",
    "RecipientProfile",
    "VerificationStatus",
    "FoodListing",
    "FoodCategory",
    "ListingStatus",
    "FoodRequest",
    "RequestStatus",
    "PickupRecord",
    "PickupStatus",
    "DistributionRecord",
    "Notification",
    "AuditLog",
    "TokenBlocklist",
]
