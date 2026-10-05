"""
Read-only access to the audit trail — Phase 11.

`AuditLog` rows have been written throughout every phase since Phase
3 (`app/utils/audit.py`'s `record_audit_log`, called from
registration, login, listing/request/pickup state changes, recipient
verification, and now account activation/deactivation). This module
is the first thing that ever *reads* that table back out — same
"read-only history" spirit as Phase 7's distribution endpoints and
Phase 10's reports, so nothing here writes anything.

Access is restricted to administrators at the route layer (spec
section 33 — "Log important actions... accessible to administrators
only"), not here.
"""

from datetime import date

from app.extensions import db
from app.models import AuditLog


class AuditQueryError(Exception):
    def __init__(self, message: str, error_code: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code


def _parse_optional_date(value, field_name: str):
    if value is None or value == "":
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise AuditQueryError(
            f"{field_name} must be a valid ISO-8601 date (YYYY-MM-DD).",
            "VALIDATION_ERROR",
            422,
        )


def list_audit_logs_query(
    *,
    user_id: int = None,
    action: str = None,
    resource_type: str = None,
    start_date_str: str = None,
    end_date_str: str = None,
):
    """
    Base (unpaginated) query over the audit trail, newest first.
    All filters are optional and combine with AND:
        user_id         the acting user's id (may be None-valued rows
                         only match if you don't filter by it — a
                         failed login with no known account never has
                         a user_id to filter on)
        action          exact match, e.g. "login_failed",
                         "account_deactivated", "request_accepted"
        resource_type   exact match, e.g. "user", "food_listing"
        start_date_str / end_date_str   ISO dates (YYYY-MM-DD),
                         inclusive, by the log entry's timestamp
    """
    start_date = _parse_optional_date(start_date_str, "start_date")
    end_date = _parse_optional_date(end_date_str, "end_date")

    if start_date is not None and end_date is not None and start_date > end_date:
        raise AuditQueryError(
            "start_date must not be after end_date.", "VALIDATION_ERROR", 422
        )

    query = db.session.query(AuditLog)

    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)
    if action:
        query = query.filter(AuditLog.action == action)
    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type)
    if start_date is not None:
        query = query.filter(db.func.date(AuditLog.timestamp) >= start_date)
    if end_date is not None:
        query = query.filter(db.func.date(AuditLog.timestamp) <= end_date)

    return query.order_by(AuditLog.timestamp.desc())
