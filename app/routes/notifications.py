"""
Notification routes (Phase 9).

    GET  /api/notifications           — my own notifications, paginated, newest first
    POST /api/notifications/<id>/read — mark one of my own notifications as read
"""

from flask import Blueprint, g, request

from app.auth.decorators import token_required
from app.services.notification_service import (
    NotificationError,
    count_unread,
    list_notifications_query,
    mark_notification_read,
)
from app.utils.pagination import get_pagination_params, paginate_query
from app.utils.responses import error_response, success_response

notifications_bp = Blueprint("notifications", __name__)


def _parse_unread_only(args) -> bool:
    return args.get("unread_only", "").strip().lower() in ("true", "1", "yes")


@notifications_bp.route("", methods=["GET"])
@token_required
def mine():
    """
    GET /api/notifications — every notification belonging to me,
    newest first.

    Query parameters (optional):
        page, limit  — standard pagination
        unread_only  — "true" to return only unread notifications
    """
    unread_only = _parse_unread_only(request.args)
    query = list_notifications_query(user=g.current_user, unread_only=unread_only)

    page, limit = get_pagination_params(request.args)
    items, pagination = paginate_query(query, page, limit)

    return success_response(
        "Notifications retrieved successfully.",
        data={
            "notifications": [n.to_dict() for n in items],
            "pagination": pagination,
            "unread_count": count_unread(user=g.current_user),
        },
    )


@notifications_bp.route("/<int:notification_id>/read", methods=["POST"])
@token_required
def mark_read(notification_id):
    """POST /api/notifications/<id>/read — owner only. Idempotent."""
    try:
        notification = mark_notification_read(
            notification_id=notification_id, user=g.current_user
        )
    except NotificationError as exc:
        return error_response(exc.message, exc.error_code, exc.status_code)

    return success_response(
        "Notification marked as read.", data=notification.to_dict()
    )
