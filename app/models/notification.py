"""
Notification model — `notifications` table.

In-app notifications for users (spec sections 22–23). No email/SMS
delivery — notifications are just rows a user can fetch via
`GET /api/notifications` and mark as read. The actual logic that
*creates* these rows (e.g. "notify provider when a request comes in")
is implemented in Phase 9, alongside the request/pickup workflows
that trigger it.
"""

from app.extensions import db
from app.models.base import utcnow


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # A short machine-readable category, e.g. "request_received",
    # "request_accepted", "pickup_confirmed", "listing_expired".
    # Kept as a plain string (not an enum) since the set of
    # notification types is expected to grow as features are added.
    notification_type = db.Column(db.String(50), nullable=False)

    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)

    # Loosely references whatever triggered the notification (a
    # listing, a request, a pickup, etc.) without a hard foreign key,
    # since it can point to different tables depending on type.
    related_resource_type = db.Column(db.String(50), nullable=True)
    related_resource_id = db.Column(db.Integer, nullable=True)

    is_read = db.Column(db.Boolean, nullable=False, default=False, index=True)

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    user = db.relationship("User", back_populates="notifications")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "notification_type": self.notification_type,
            "title": self.title,
            "message": self.message,
            "related_resource_type": self.related_resource_type,
            "related_resource_id": self.related_resource_id,
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<Notification id={self.id} user_id={self.user_id} type={self.notification_type!r}>"
