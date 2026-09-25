"""
Authentication routes.

    POST /api/auth/register
    POST /api/auth/login
    POST /api/auth/logout   (protected)

Route handlers here stay thin: parse the request body, call the
service layer (app/services/auth_service.py) for the actual business
logic, and translate the result into the project's standard JSON
response shape.
"""

from flask import Blueprint, g, request

from app.auth.decorators import token_required
from app.extensions import db
from app.middleware.rate_limit import rate_limit
from app.models import TokenBlocklist
from app.services.auth_service import AuthError, authenticate_user, register_user
from app.utils.audit import record_audit_log
from app.utils.responses import error_response, success_response

auth_bp = Blueprint("auth", __name__)

# Phase 11: both endpoints below are reachable with no token at all,
# which makes them the two most attractive targets for automated
# abuse (password brute-forcing, registration spam) — see
# app/middleware/rate_limit.py for why this stays in-memory rather
# than pulling in a new dependency.
_LOGIN_RATE_LIMIT = dict(max_requests=10, window_seconds=300, bucket="auth_login")
_REGISTER_RATE_LIMIT = dict(max_requests=5, window_seconds=300, bucket="auth_register")


@auth_bp.route("/register", methods=["POST"])
@rate_limit(**_REGISTER_RATE_LIMIT)
def register():
    """
    POST /api/auth/register

    Body:
        {
            "name": "Green Table Restaurant",
            "email": "contact@greentable.example",
            "password": "SecurePass123",
            "role": "provider"   // or "recipient" — never "admin"
        }
    """
    body = request.get_json(silent=True) or {}

    try:
        user = register_user(
            name=body.get("name"),
            email=body.get("email"),
            password=body.get("password"),
            role=body.get("role"),
        )
    except AuthError as exc:
        return error_response(exc.message, exc.error_code, exc.status_code)

    return success_response(
        "Account registered successfully.", data=user.to_dict(), status_code=201
    )


@auth_bp.route("/login", methods=["POST"])
@rate_limit(**_LOGIN_RATE_LIMIT)
def login():
    """
    POST /api/auth/login

    Body:
        {"email": "contact@greentable.example", "password": "SecurePass123"}

    On success, returns a JWT the client must send as
    `Authorization: Bearer <token>` on every subsequent protected
    request.
    """
    body = request.get_json(silent=True) or {}

    try:
        user, token = authenticate_user(
            email=body.get("email"), password=body.get("password")
        )
    except AuthError as exc:
        return error_response(exc.message, exc.error_code, exc.status_code)

    return success_response(
        "Login successful.",
        data={"token": token, "user": user.to_dict()},
    )


@auth_bp.route("/logout", methods=["POST"])
@token_required
def logout():
    """
    POST /api/auth/logout   (requires Authorization: Bearer <token>)

    JWTs can't be deleted, so "logout" works by recording this
    specific token's ID (jti) in the blocklist — every future request
    with this exact token will then be rejected by @token_required,
    even though the token itself hasn't expired yet.
    """
    jti = g.current_token_jti
    if jti:
        db.session.add(TokenBlocklist(jti=jti, user_id=g.current_user.id))

    record_audit_log(
        user_id=g.current_user.id,
        action="logout",
        resource_type="user",
        resource_id=g.current_user.id,
        description="User logged out.",
    )
    db.session.commit()

    return success_response("Logged out successfully.")
