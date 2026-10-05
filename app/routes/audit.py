"""
Audit log routes — Phase 11.

    GET /api/audit-logs   — admin only: the full audit trail, filterable, paginated

This is the endpoint promised back in Phase 10's README preview:
"Exposing the AuditLog model ... via admin-only read endpoints."
Read-only, same as app/routes/reports.py and app/routes/distributions.py.
"""

from flask import Blueprint, request

from app.auth.decorators import role_required, token_required
from app.models import UserRole
from app.services.audit_service import AuditQueryError, list_audit_logs_query
from app.utils.pagination import get_pagination_params, paginate_query
from app.utils.responses import error_response, success_response

audit_bp = Blueprint("audit", __name__)


@audit_bp.route("", methods=["GET"])
@token_required
@role_required(UserRole.ADMIN)
def list_audit_logs():
    """
    GET /api/audit-logs   (admin only)

    Query parameters (all optional):
        user_id         filter to one acting user's entries
        action          exact match, e.g. "login_failed", "account_deactivated"
        resource_type   exact match, e.g. "user", "food_listing"
        start_date, end_date   ISO dates (YYYY-MM-DD), inclusive, by timestamp
        page, limit     standard pagination
    """
    try:
        query = list_audit_logs_query(
            user_id=request.args.get("user_id", type=int),
            action=request.args.get("action"),
            resource_type=request.args.get("resource_type"),
            start_date_str=request.args.get("start_date"),
            end_date_str=request.args.get("end_date"),
        )
    except AuditQueryError as exc:
        return error_response(exc.message, exc.error_code, exc.status_code)

    page, limit = get_pagination_params(request.args)
    items, pagination = paginate_query(query, page, limit)

    return success_response(
        "Audit logs retrieved successfully.",
        data={
            "audit_logs": [entry.to_dict() for entry in items],
            "pagination": pagination,
        },
    )
