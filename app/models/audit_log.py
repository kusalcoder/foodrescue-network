"""
AuditLog model — `audit_logs` table.

An append-only trail of security- and business-relevant actions
(spec section 33): logins, registrations, listing changes, request
decisions, pickups, account activation/deactivation, etc.

`user_id` is nullable because some actions worth auditing (e.g. a
failed login attempt with a bad email) may not correspond to a known,
authenticated user.

Actual log-writing calls happen throughout the service layer starting
in Phase 3 (first entries: registration, login) and continuing through
every later phase. Access to this table is restricted to
administrators — enforced in the route/authorization layer, not here.
"""

from app.extensions import db
from app.models.base import utcnow


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # e.g. "login", "user_registered", "listing_created",
    # "request_accepted", "pickup_confirmed", "account_deactivated"
    action = db.Column(db.String(100), nullable=False, index=True)

    # e.g. "food_listing", "food_request", "user" — identifies which
    # kind of resource `resource_id` refers to.
    resource_type = db.Column(db.String(50), nullable=True)
    resource_id = db.Column(db.Integer, nullable=True)

    description = db.Column(db.Text, nullable=True)

    timestamp = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    user = db.relationship("User", back_populates="audit_logs")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "description": self.description,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }

    def __repr__(self):
        return f"<AuditLog id={self.id} action={self.action!r}>"
