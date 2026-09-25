"""
Shared input-validation helpers.

Kept as small, dependency-free functions (rather than a full schema
library like marshmallow, added in a later phase) so Phase 3 doesn't
need to introduce a new dependency just for two fields. Each
validator returns an error message string on failure, or `None` on
success — that convention is used consistently across all validators
so route code can do:

    error = validate_email(email)
    if error:
        return error_response(error)
"""

import re

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

MIN_PASSWORD_LENGTH = 8


def validate_email(email: str):
    if not email or not isinstance(email, str):
        return "Email is required."
    if not _EMAIL_PATTERN.match(email.strip()):
        return "Email format is invalid."
    return None


def validate_password(password: str):
    if not password or not isinstance(password, str):
        return "Password is required."
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"[0-9]", password):
        return "Password must contain both letters and numbers."
    return None


def validate_name(name: str):
    if not name or not isinstance(name, str) or not name.strip():
        return "Name is required."
    if len(name.strip()) > 150:
        return "Name must be 150 characters or fewer."
    return None


def validate_role(role: str, allowed_roles):
    """
    `allowed_roles` is the set of role *values* (strings) a caller may
    self-register as. Administrators are deliberately excluded from
    this set wherever it's used for public registration (spec section
    5 — "Normal registration must not allow users to create
    administrator accounts themselves").
    """
    if not role or not isinstance(role, str):
        return "Role is required."
    if role not in allowed_roles:
        return f"Role must be one of: {', '.join(allowed_roles)}."
    return None


def validate_coordinates(latitude, longitude):
    """
    Both latitude and longitude are optional ("where available" per
    spec), but if either is supplied, it must be a valid number
    within range — and it doesn't make sense to supply only one.
    """
    if latitude is None and longitude is None:
        return None

    if latitude is None or longitude is None:
        return "Both latitude and longitude must be provided together."

    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return "Latitude and longitude must be numbers."

    if not (-90 <= lat <= 90):
        return "Latitude must be between -90 and 90."
    if not (-180 <= lon <= 180):
        return "Longitude must be between -180 and 180."
    return None


def validate_positive_number(value, field_name: str):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return f"{field_name} must be a number."
    if number <= 0:
        return f"{field_name} must be greater than zero."
    return None
