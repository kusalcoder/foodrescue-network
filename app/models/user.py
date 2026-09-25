"""
User model — `users` table.

This is the core identity table. Every Provider, Recipient, and
Administrator is a `User` first; the role determines which "profile"
table (ProviderProfile / RecipientProfile) they additionally have a
row in.

Password hashing itself is implemented in Phase 3 (Authentication).
For now this model only defines the *storage* for a hash — it does
not yet contain the hashing logic.
"""

import enum

from app.extensions import db
from app.models.base import TimestampMixin


class UserRole(enum.Enum):
    """
    The three roles required by the spec (section 3).

    Stored as a native PostgreSQL ENUM type for data integrity: the
    database itself will reject an invalid role value, not just the
    application code.
    """

    PROVIDER = "provider"
    RECIPIENT = "recipient"
    ADMIN = "admin"


class AccountStatus(enum.Enum):
    """
    Whether a user's account is currently allowed to log in / act.

    Administrators can deactivate accounts (spec section 3 —
    "Activate/deactivate accounts"). A deactivated user should be
    blocked at the authentication layer in Phase 3.
    """

    ACTIVE = "active"
    INACTIVE = "inactive"


class User(db.Model, TimestampMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(150), nullable=False)

    # unique=True creates a UNIQUE constraint at the database level —
    # required by spec section 5 ("Email should be unique").
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)

    # Only ever stores a HASH, never the plaintext password.
    # The column name makes that explicit so nobody is tempted to
    # put raw passwords in it.
    password_hash = db.Column(db.String(255), nullable=False)

    role = db.Column(
        db.Enum(UserRole, name="user_role"),
        nullable=False,
    )

    status = db.Column(
        db.Enum(AccountStatus, name="account_status"),
        nullable=False,
        default=AccountStatus.ACTIVE,
    )

    # One-to-one relationships to the role-specific profile tables.
    # `uselist=False` makes these behave as a single object rather
    # than a list, e.g. `user.provider_profile.org_name`.
    provider_profile = db.relationship(
        "ProviderProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    recipient_profile = db.relationship(
        "RecipientProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )

    # A user can have many notifications and many audit log entries.
    notifications = db.relationship(
        "Notification", back_populates="user", cascade="all, delete-orphan"
    )
    audit_logs = db.relationship("AuditLog", back_populates="user")

    def to_dict(self):
        """
        Safe dictionary representation for JSON responses.

        Deliberately EXCLUDES password_hash — per spec section 4:
        "Never return password hashes in API responses."
        """
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "role": self.role.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<User id={self.id} email={self.email!r} role={self.role}>"
