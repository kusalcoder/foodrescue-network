"""
Distribution history routes (read-only — see
app/services/distribution_service.py for why).

    GET /api/distributions       — my own distribution history (provider or recipient)
    GET /api/distributions/<id>  — view one (owning provider OR owning recipient)
"""

from flask import Blueprint, g, request

from app.auth.decorators import role_required, token_required
from app.models import UserRole
from app.services.distribution_service import (
    DistributionError,
    get_distribution_for_viewer,
    list_distributions_query,
)
from app.utils.pagination import get_pagination_params, paginate_query
from app.utils.responses import error_response, success_response

distributions_bp = Blueprint("distributions", __name__)


@distributions_bp.route("", methods=["GET"])
@token_required
@role_required(UserRole.PROVIDER, UserRole.RECIPIENT)
def mine():
    """
    GET /api/distributions — every completed distribution involving
    me, as either the provider or the recipient.

    Query parameters (optional): page, limit.
    """
    query = list_distributions_query(current_user=g.current_user)
    if query is None:
        return error_response(
            "Complete a provider or recipient profile first.",
            "PROFILE_NOT_FOUND",
            404,
        )

    page, limit = get_pagination_params(request.args)
    items, pagination = paginate_query(query, page, limit)
    return success_response(
        "Distribution history retrieved successfully.",
        data={
            "distributions": [d.to_dict() for d in items],
            "pagination": pagination,
        },
    )


@distributions_bp.route("/<int:distribution_id>", methods=["GET"])
@token_required
def get_one(distribution_id):
    """GET /api/distributions/<id> — owning provider or owning recipient only."""
    try:
        record = get_distribution_for_viewer(
            distribution_id=distribution_id, current_user=g.current_user
        )
    except DistributionError as exc:
        return error_response(exc.message, exc.error_code, exc.status_code)

    return success_response(
        "Distribution record retrieved successfully.", data=record.to_dict()
    )
