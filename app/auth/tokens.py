"""
JWT (JSON Web Token) utilities for authentication.

We use JWTs so that after logging in once, a client (Postman, a
future frontend, etc.) can prove who it is on every subsequent
request by sending the token in an `Authorization: Bearer <token>`
header — without the server needing to keep a server-side session
for every logged-in user.

Each token embeds:
    - `sub`  : the user's ID (JWT standard claim name for "subject")
    - `role` : the user's role, so authorization checks don't need an
               extra database lookup on every single request
    - `jti`  : a unique token ID, used to support logout (see
               app/auth/blocklist.py) — JWTs are normally stateless
               and can't be "deleted", so logout works by remembering
               that this specific token's jti has been revoked
    - `iat`  : issued-at time
    - `exp`  : expiry time
"""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from flask import current_app

# How long a token stays valid after login. Kept short-ish (24 hours)
# since there is no refresh-token flow in this academic-scope project
# — after expiry, the client just logs in again.
TOKEN_EXPIRY_HOURS = 24


def generate_token(user_id: int, role: str) -> str:
    """
    Create a signed JWT for a newly authenticated user.

    The token is signed with the app's SECRET_KEY (from environment
    variables — see app/config.py), so only this server can produce
    tokens that will pass verification.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(hours=TOKEN_EXPIRY_HOURS),
    }
    return jwt.encode(payload, current_app.config["SECRET_KEY"], algorithm="HS256")


class TokenError(Exception):
    """Raised for any problem with a token: expired, malformed, or
    signed with a different key. Callers treat this uniformly as
    'authentication failed' — the specific reason is for logs only,
    never returned to the client (that would help an attacker probe
    the auth system)."""


def decode_token(token: str) -> dict:
    """
    Verify a token's signature and expiry, and return its payload.

    Raises TokenError for any invalid token so callers have one
    simple exception to catch.
    """
    try:
        return jwt.decode(
            token, current_app.config["SECRET_KEY"], algorithms=["HS256"]
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Token is invalid") from exc
