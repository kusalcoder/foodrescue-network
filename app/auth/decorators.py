"""
Authentication & authorization decorators.

`@token_required` — attach to any route that requires a logged-in
user. Reads the `Authorization: Bearer <token>` header, verifies it,
checks it hasn't been logged out (blocklist), checks the user's
account is still active, and stores the current user on Flask's
request-local `g` object as `g.current_user` for the route to use.

`@role_required(...)` — stack on top of `@token_required` to further
restrict a route to specific roles (e.g. only ADMIN, or only
PROVIDER). This is the "role-level" half of authorization (spec
section 32); "resource-level" checks (e.g. "is this YOUR listing?")
are the route/service's own responsibility on top of this.
"""

from functools import wraps

from flask import g, jsonify, request

from app.auth.tokens import TokenError, decode_token
from app.extensions import db
from app.models import AccountStatus, TokenBlocklist, User


def _unauthorized(message: str, error_code: str = "UNAUTHORIZED"):
    return (
        jsonify(success=False, message=message, error=error_code),
        401,
    )


def token_required(view_func):
    """
    Require a valid, non-revoked JWT for this route.

    On success, sets `g.current_user` (a `User` model instance) and
    `g.current_token_jti` (useful for the logout endpoint) before
    calling the wrapped view.
    """

    @wraps(view_func)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Bearer "):
            return _unauthorized(
                "Authentication required. Provide a Bearer token.",
                "AUTH_HEADER_MISSING",
            )

        token = auth_header.split(" ", 1)[1].strip()

        try:
            payload = decode_token(token)
        except TokenError:
            return _unauthorized("Invalid or expired token.", "TOKEN_INVALID")

        jti = payload.get("jti")
        if jti is not None:
            is_revoked = (
                db.session.query(TokenBlocklist.id)
                .filter_by(jti=jti)
                .first()
                is not None
            )
            if is_revoked:
                return _unauthorized(
                    "This token has been logged out.", "TOKEN_REVOKED"
                )

        user = db.session.get(User, int(payload["sub"]))
        if user is None:
            return _unauthorized("User account no longer exists.", "USER_NOT_FOUND")

        if user.status != AccountStatus.ACTIVE:
            return _unauthorized(
                "This account has been deactivated.", "ACCOUNT_INACTIVE"
            )

        g.current_user = user
        g.current_token_jti = jti

        return view_func(*args, **kwargs)

    return wrapper


def role_required(*allowed_roles):
    """
    Restrict a route to one or more roles.

    Usage:
        @auth_bp.route("/some-admin-only-thing")
        @token_required
        @role_required(UserRole.ADMIN)
        def admin_only():
            ...

    Must be stacked BELOW @token_required (i.e. applied first / closer
    to the function) so that `g.current_user` already exists — in
    Python decorator order that means @token_required goes above
    @role_required in the source.
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            user = getattr(g, "current_user", None)
            if user is None:
                # Defensive: this should never happen if
                # @token_required was applied, but fail safely.
                return _unauthorized("Authentication required.")

            if user.role not in allowed_roles:
                return (
                    jsonify(
                        success=False,
                        message="You do not have permission to perform this action.",
                        error="FORBIDDEN",
                    ),
                    403,
                )
            return view_func(*args, **kwargs)

        return wrapper

    return decorator
