"""
Audit logging helper.

A single `record_audit_log()` function used by every phase from here
on, so audit entries always have the same shape (spec section 33).
It only stages the new row with `db.session.add()` — it deliberately
does NOT commit, so it can be called in the middle of a larger
transaction (e.g. "create the listing AND log it, as one atomic
unit" — see Phase 6's request-acceptance flow) without prematurely
ending that transaction. The caller commits.
"""

from app.extensions import db
from app.models import AuditLog


def record_audit_log(
    *,
    user_id: int | None,
    action: str,
    resource_type: str | None = None,
    resource_id: int | None = None,
    description: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        description=description,
    )
    db.session.add(entry)
    return entry
