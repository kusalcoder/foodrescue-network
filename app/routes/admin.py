"""
Administrator user-management routes — Phase 11.

    GET  /api/admin/users                 — list/filter every user account
    GET  /api/admin/users/<id>             — view one user's account details
    POST /api/admin/users/<id>/deactivate  — suspend an account
    POST /api/admin/users/<id>/activate    — reactivate an account

Everything here is admin-only. This is the "broader user management,
account activation/deactivation" piece that Phase 6's minimal
`POST /api/recipients/<id>/verify` route explicitly deferred to a
later phase.
"""

from flask import Blueprint, g, request

from app.auth.decorators import role_required, token_required
from app.models import UserRole
from app.services.admin_service import (
    AdminError,
    activate_user,
    deactivate_user,
    get_user_or_404,
    list_users_query,
)
from app.utils.pagination import get_pagination_params, paginate_query
from app.utils.responses import error_response, success_response

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/users", methods=["GET"])
@token_required
@role_required(UserRole.ADMIN)
def list_users():
    """
    GET /api/admin/users   (admin only)

    Query parameters (all optional):
        role     "provider" | "recipient" | "admin"
        status   "active" | "inactive"
        search   case-insensitive substring match against name or email
        page, limit   standard pagination
    """
    try:
        query = list_users_query(
            role=request.args.get("role"),
            status=request.args.get("status"),
            search=request.args.get("search"),
        )
    except AdminError as exc:
        return error_response(exc.message, exc.error_code, exc.status_code)

    page, limit = get_pagination_params(request.args)
    items, pagination = paginate_query(query, page, limit)

    return success_response(
        "Users retrieved successfully.",
        data={"users": [u.to_dict() for u in items], "pagination": pagination},
    )


@admin_bp.route("/users/<int:user_id>", methods=["GET"])
@token_required
@role_required(UserRole.ADMIN)
def get_user(user_id):
    """GET /api/admin/users/<id>   (admin only)"""
    try:
        user = get_user_or_404(user_id)
    except AdminError as exc:
        return error_response(exc.message, exc.error_code, exc.status_code)

    return success_response("User retrieved successfully.", data=user.to_dict())


@admin_bp.route("/users/<int:user_id>/deactivate", methods=["POST"])
@token_required
@role_required(UserRole.ADMIN)
def deactivate(user_id):
    """POST /api/admin/users/<id>/deactivate   (admin only)"""
    try:
        user = deactivate_user(target_user_id=user_id, admin_user_id=g.current_user.id)
    except AdminError as exc:
        return error_response(exc.message, exc.error_code, exc.status_code)

    return success_response("Account deactivated successfully.", data=user.to_dict())


@admin_bp.route("/users/<int:user_id>/activate", methods=["POST"])
@token_required
@role_required(UserRole.ADMIN)
def activate(user_id):
    """POST /api/admin/users/<id>/activate   (admin only)"""
    try:
        user = activate_user(target_user_id=user_id, admin_user_id=g.current_user.id)
    except AdminError as exc:
        return error_response(exc.message, exc.error_code, exc.status_code)

    return success_response("Account reactivated successfully.", data=user.to_dict())
