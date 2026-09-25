"""
Reporting routes (Phase 10).

    GET /api/reports/distributions/summary       — totals (admin: platform-wide by default; provider/recipient: own only)
    GET /api/reports/distributions/by-category    — same scope, broken down by food category
    GET /api/reports/my-activity                  — provider/recipient: my own full activity dashboard
    GET /api/reports/platform-summary              — admin only: users/listings/recipients snapshot

Every endpoint here is read-only — it summarizes DistributionRecord/
FoodRequest/PickupRecord/FoodListing rows that other phases already
created, the same "read-only history" spirit as Phase 7's
/api/distributions endpoints.

Scoping rules (who can see whose numbers):
    - A provider always sees only THEIR OWN data — provider_id/
      recipient_id query params are ignored for them, not honored,
      so there's no way to peek at another provider's numbers by
      passing a different id.
    - A recipient always sees only THEIR OWN data, same reasoning.
    - An admin sees platform-wide data by default, but MAY narrow it
      to a specific provider_id and/or recipient_id via query params
      (e.g. auditing one organization).
"""

from flask import Blueprint, g, request

from app.auth.decorators import role_required, token_required
from app.models import UserRole
from app.reports.service import (
    ReportError,
    distribution_by_category,
    distribution_summary,
    parse_optional_date,
    platform_summary,
    provider_activity_summary,
    recipient_activity_summary,
)
from app.utils.responses import error_response, success_response

reports_bp = Blueprint("reports", __name__)


def _resolve_distribution_scope():
    """
    Returns (provider_id, recipient_id, error_response_or_None).

    Providers/recipients are pinned to their own profile id and may
    not override it. Admins may optionally pass provider_id and/or
    recipient_id query params to narrow the report; omitting both
    means platform-wide.
    """
    user = g.current_user

    if user.role == UserRole.PROVIDER:
        if user.provider_profile is None:
            return None, None, error_response(
                "Complete your provider profile before viewing reports.",
                "PROFILE_NOT_FOUND",
                404,
            )
        return user.provider_profile.id, None, None

    if user.role == UserRole.RECIPIENT:
        if user.recipient_profile is None:
            return None, None, error_response(
                "Complete your recipient profile before viewing reports.",
                "PROFILE_NOT_FOUND",
                404,
            )
        return None, user.recipient_profile.id, None

    # Admin: optional explicit filters, otherwise platform-wide.
    provider_id = request.args.get("provider_id", type=int)
    recipient_id = request.args.get("recipient_id", type=int)
    return provider_id, recipient_id, None


def _parse_date_range():
    """Returns (start_date, end_date, error_response_or_None)."""
    try:
        start_date = parse_optional_date(request.args.get("start_date"), "start_date")
        end_date = parse_optional_date(request.args.get("end_date"), "end_date")
    except ReportError as exc:
        return None, None, error_response(exc.message, exc.error_code, exc.status_code)
    return start_date, end_date, None


@reports_bp.route("/distributions/summary", methods=["GET"])
@token_required
@role_required(UserRole.ADMIN, UserRole.PROVIDER, UserRole.RECIPIENT)
def distributions_summary_route():
    """
    GET /api/reports/distributions/summary

    Query parameters (all optional):
        start_date, end_date   ISO dates (YYYY-MM-DD), inclusive, by pickup date
        provider_id, recipient_id   admin only — narrows the report
    """
    provider_id, recipient_id, scope_error = _resolve_distribution_scope()
    if scope_error:
        return scope_error

    start_date, end_date, date_error = _parse_date_range()
    if date_error:
        return date_error

    try:
        summary = distribution_summary(
            provider_id=provider_id,
            recipient_id=recipient_id,
            start_date=start_date,
            end_date=end_date,
        )
    except ReportError as exc:
        return error_response(exc.message, exc.error_code, exc.status_code)

    return success_response(
        "Distribution summary retrieved successfully.", data=summary
    )


@reports_bp.route("/distributions/by-category", methods=["GET"])
@token_required
@role_required(UserRole.ADMIN, UserRole.PROVIDER, UserRole.RECIPIENT)
def distributions_by_category_route():
    """
    GET /api/reports/distributions/by-category

    Same query parameters and scoping rules as
    /api/reports/distributions/summary.
    """
    provider_id, recipient_id, scope_error = _resolve_distribution_scope()
    if scope_error:
        return scope_error

    start_date, end_date, date_error = _parse_date_range()
    if date_error:
        return date_error

    try:
        breakdown = distribution_by_category(
            provider_id=provider_id,
            recipient_id=recipient_id,
            start_date=start_date,
            end_date=end_date,
        )
    except ReportError as exc:
        return error_response(exc.message, exc.error_code, exc.status_code)

    return success_response(
        "Distribution breakdown by category retrieved successfully.",
        data={"categories": breakdown},
    )


@reports_bp.route("/my-activity", methods=["GET"])
@token_required
@role_required(UserRole.PROVIDER, UserRole.RECIPIENT)
def my_activity_route():
    """
    GET /api/reports/my-activity

    My own full activity dashboard — listings/requests/pickups by
    status, plus total quantity distributed or received. Shape
    differs by role (a provider has no "quantity received" concept,
    a recipient has no "listings" concept), so this always reflects
    the caller's own role rather than taking one.
    """
    user = g.current_user

    if user.role == UserRole.PROVIDER:
        if user.provider_profile is None:
            return error_response(
                "Complete your provider profile before viewing your activity.",
                "PROFILE_NOT_FOUND",
                404,
            )
        summary = provider_activity_summary(provider_profile=user.provider_profile)
    else:
        if user.recipient_profile is None:
            return error_response(
                "Complete your recipient profile before viewing your activity.",
                "PROFILE_NOT_FOUND",
                404,
            )
        summary = recipient_activity_summary(recipient_profile=user.recipient_profile)

    return success_response("Activity summary retrieved successfully.", data=summary)


@reports_bp.route("/platform-summary", methods=["GET"])
@token_required
@role_required(UserRole.ADMIN)
def platform_summary_route():
    """GET /api/reports/platform-summary — admin only, all-time platform snapshot."""
    return success_response(
        "Platform summary retrieved successfully.", data=platform_summary()
    )
