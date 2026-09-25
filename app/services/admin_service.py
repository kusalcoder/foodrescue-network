"""
Administrator user-management business logic — Phase 11.

Phase 6 already introduced the smallest possible admin action
(`recipient_service.verify_recipient_profile`) purely because the
request workflow couldn't be tested without it, and deliberately
deferred "broader user management, account activation/deactivation,
audit log access" to a later phase (see the docstring on
`POST /api/recipients/<id>/verify`). This module is that later phase.

Deactivating a user does not need to touch any JWT/blocklist state:
`app/auth/decorators.py`'s `token_required` already rejects every
request from a non-ACTIVE account on every call, so flipping
`status` here takes effect on the user's very next request, even if
they're still holding an unexpired token.
"""

from app.extensions import db
from app.models import AccountStatus, User, UserRole
from app.services.notification_service import create_notification
from app.utils.audit import record_audit_log

VALID_ROLE_FILTERS = {role.value for role in UserRole}
VALID_STATUS_FILTERS = {status.value for status in AccountStatus}


class AdminError(Exception):
    def __init__(self, message: str, error_code: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code


def list_users_query(*, role: str = None, status: str = None, search: str = None):
    """
    Base (unpaginated) query over every user account, newest first.
    All filters are optional and combine with AND:
        role    one of "provider" / "recipient" / "admin"
        status  one of "active" / "inactive"
        search  case-insensitive substring match against name or email
    """
    query = db.session.query(User)

    if role is not None:
        if role not in VALID_ROLE_FILTERS:
            raise AdminError(
                f"role must be one of: {', '.join(sorted(VALID_ROLE_FILTERS))}.",
                "VALIDATION_ERROR",
                422,
            )
        query = query.filter(User.role == UserRole(role))

    if status is not None:
        if status not in VALID_STATUS_FILTERS:
            raise AdminError(
                f"status must be one of: {', '.join(sorted(VALID_STATUS_FILTERS))}.",
                "VALIDATION_ERROR",
                422,
            )
        query = query.filter(User.status == AccountStatus(status))

    if search:
        pattern = f"%{search.strip().lower()}%"
        query = query.filter(
            db.or_(
                db.func.lower(User.name).like(pattern),
                db.func.lower(User.email).like(pattern),
            )
        )

    return query.order_by(User.created_at.desc())


def get_user_or_404(user_id: int) -> User:
    user = db.session.get(User, user_id)
    if user is None:
        raise AdminError("User not found.", "USER_NOT_FOUND", 404)
    return user


def deactivate_user(*, target_user_id: int, admin_user_id: int) -> User:
    """
    Suspend a user account (spec section 3 — "Activate/deactivate
    accounts"). Idempotent: deactivating an already-inactive account
    is a no-op success, not an error, matching the pattern already
    established by `notification_service.mark_notification_read`.

    Refuses to let an admin deactivate their own account — with no
    other admin action available to reverse it, that would be a
    self-inflicted lockout with no recovery path short of touching
    the database directly.
    """
    if target_user_id == admin_user_id:
        raise AdminError(
            "You cannot deactivate your own account.",
            "CANNOT_DEACTIVATE_SELF",
            400,
        )

    user = get_user_or_404(target_user_id)

    if user.status == AccountStatus.INACTIVE:
        return user

    user.status = AccountStatus.INACTIVE

    create_notification(
        user_id=user.id,
        notification_type="account_deactivated",
        title="Your account has been deactivated",
        message="An administrator has deactivated your account. Contact support if you believe this is a mistake.",
    )
    record_audit_log(
        user_id=admin_user_id,
        action="account_deactivated",
        resource_type="user",
        resource_id=user.id,
        description=f"Administrator deactivated account {user.email!r}.",
    )
    db.session.commit()
    return user


def activate_user(*, target_user_id: int, admin_user_id: int) -> User:
    """Reverse of deactivate_user — also idempotent."""
    user = get_user_or_404(target_user_id)

    if user.status == AccountStatus.ACTIVE:
        return user

    user.status = AccountStatus.ACTIVE

    create_notification(
        user_id=user.id,
        notification_type="account_reactivated",
        title="Your account has been reactivated",
        message="An administrator has reactivated your account. You can log in again.",
    )
    record_audit_log(
        user_id=admin_user_id,
        action="account_reactivated",
        resource_type="user",
        resource_id=user.id,
        description=f"Administrator reactivated account {user.email!r}.",
    )
    db.session.commit()
    return user
