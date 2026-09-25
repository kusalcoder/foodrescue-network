"""
GET /api/profile — a minimal protected endpoint (spec section 27).

Returns the currently authenticated user's own account info. This is
intentionally the simplest possible "protected route" — it exists in
Phase 3 mainly to prove the authentication/authorization machinery
works end-to-end before Phase 4/5 build the richer, role-specific
provider/recipient profile endpoints on top of the same
`@token_required` decorator.
"""

from flask import Blueprint, g

from app.auth.decorators import token_required
from app.utils.responses import success_response

profile_bp = Blueprint("profile", __name__)


@profile_bp.route("/profile", methods=["GET"])
@token_required
def get_profile():
    return success_response(
        "Profile retrieved successfully.", data=g.current_user.to_dict()
    )
