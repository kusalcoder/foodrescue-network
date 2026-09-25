"""
Notification business logic (Phase 9 — spec sections 22-23).

The `Notification` model itself was scaffolded back in Phase 2. This
phase adds the logic that actually creates rows in it, and the
read/mark-as-read operations a user performs on their own
notifications.

`create_notification()` mirrors `record_audit_log()`'s shape on
purpose: it only stages the row with `db.session.add()` and does NOT
commit. That lets every lifecycle event that should fire a
notification (a request being accepted, a pickup being scheduled,
...) call it from the *middle* of an existing service transaction —
e.g. `request_service.accept_request()` — and have the notification
land atomically with the state change it describes, committed once
by that transaction's own `db.session.commit()`. If the notification
were committed separately, it would be possible (on a crash between
the two commits) for a user to see "request accepted" with no
notification, or a notification for a change that then failed to
save.

This phase is deliberately in-app only — no email/SMS delivery (see
the README's Phase 9 preview). `notification_type` stays a plain
string, not an enum, since (per the model's own docstring) the set
of event types is expected to keep growing as more of the platform
gets built.
"""

from app.extensions import db
from app.models import Notification


class NotificationError(Exception):
    def __init__(self, message: str, error_code: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code


def create_notification(
    *,
    user_id: int,
    notification_type: str,
    title: str,
    message: str,
    related_resource_type: str = None,
    related_resource_id: int = None,
) -> Notification:
    """
    Stage a new notification for `user_id`. Does NOT commit — see the
    module docstring for why. The caller (whatever service triggered
    the event) is responsible for committing.
    """
    notification = Notification(
        user_id=user_id,
        notification_type=notification_type,
        title=title,
        message=message,
        related_resource_type=related_resource_type,
        related_resource_id=related_resource_id,
    )
    db.session.add(notification)
    return notification


def list_notifications_query(*, user, unread_only: bool = False):
    """
    Base (unpaginated) query of a user's own notifications, newest
    first. Every user (regardless of role) can have notifications, so
    unlike the pickup/distribution queries this needs no profile
    lookup — it's scoped directly by `user.id`.
    """
    query = db.session.query(Notification).filter(Notification.user_id == user.id)
    if unread_only:
        query = query.filter(Notification.is_read.is_(False))
    return query.order_by(Notification.created_at.desc())


def count_unread(*, user) -> int:
    return (
        db.session.query(db.func.count(Notification.id))
        .filter(Notification.user_id == user.id, Notification.is_read.is_(False))
        .scalar()
        or 0
    )


def mark_notification_read(*, notification_id: int, user) -> Notification:
    """
    Mark one of the current user's own notifications as read.
    Idempotent — marking an already-read notification just returns it
    unchanged rather than erroring, since "read" isn't a workflow
    state with rules attached (unlike, say, a request or pickup
    status) and there's no meaningful failure mode to report here.
    """
    notification = db.session.get(Notification, notification_id)
    if notification is None:
        raise NotificationError(
            "Notification not found.", "NOTIFICATION_NOT_FOUND", 404
        )

    if notification.user_id != user.id:
        raise NotificationError(
            "You do not have permission to view this notification.",
            "FORBIDDEN",
            403,
        )

    if not notification.is_read:
        notification.is_read = True
        db.session.commit()
    return notification
