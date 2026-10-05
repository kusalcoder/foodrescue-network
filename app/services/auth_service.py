"""
Authentication business logic.

Kept separate from `app/routes/auth.py` (which only handles HTTP
concerns: parsing the request, calling this service, and formatting
the response) so the actual registration/login rules can be unit
tested in Phase 12 without spinning up a Flask test client.
"""

from app.auth.security import hash_password, verify_password
from app.auth.tokens import generate_token
from app.extensions import db
from app.models import AccountStatus, User, UserRole
from app.utils.audit import record_audit_log
from app.utils.validation import (
    validate_email,
    validate_name,
    validate_password,
    validate_role,
)

# Roles a person may self-assign during public registration.
# ADMIN is deliberately excluded — spec section 5: "Normal
# registration must not allow users to create administrator accounts
# themselves." Admin accounts are created some other way (e.g.
# directly in the database, or by an existing admin) — that's outside
# the scope of the public registration endpoint.
SELF_REGISTERABLE_ROLES = {UserRole.PROVIDER.value, UserRole.RECIPIENT.value}


class AuthError(Exception):
    """
    Raised for any registration/login failure that should be shown to
    the client. Carries both a safe message and a machine-readable
    error code, and the HTTP status the route should respond with.
    """

    def __init__(self, message: str, error_code: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code


def register_user(*, name: str, email: str, password: str, role: str) -> User:
    """
    Validate and create a new user account.

    Raises AuthError on any validation failure or duplicate email.
    Does not create a ProviderProfile/RecipientProfile row — that
    happens in Phase 4/5 via a separate "create my profile" endpoint,
    keeping "create an account" and "fill in my organization details"
    as two distinct, independently-retryable steps.
    """
    for error in (
        validate_name(name),
        validate_email(email),
        validate_password(password),
        validate_role(role, SELF_REGISTERABLE_ROLES),
    ):
        if error:
            raise AuthError(error, "VALIDATION_ERROR", 422)

    normalized_email = email.strip().lower()

    existing = db.session.query(User).filter_by(email=normalized_email).first()
    if existing:
        raise AuthError(
            "An account with this email already exists.",
            "EMAIL_ALREADY_REGISTERED",
            409,
        )

    user = User(
        name=name.strip(),
        email=normalized_email,
        password_hash=hash_password(password),
        role=UserRole(role),
        status=AccountStatus.ACTIVE,
    )
    db.session.add(user)
    db.session.flush()  # assigns user.id without ending the transaction

    record_audit_log(
        user_id=user.id,
        action="user_registered",
        resource_type="user",
        resource_id=user.id,
        description=f"New {role} account registered.",
    )

    db.session.commit()
    return user


def authenticate_user(*, email: str, password: str) -> tuple[User, str]:
    """
    Verify credentials and return (user, token) on success.

    Raises AuthError on any failure. Deliberately uses the SAME error
    message and code ("Invalid email or password") whether the email
    doesn't exist or the password is wrong — revealing which one it
    was would let an attacker enumerate registered email addresses.
    """
    if not email or not password:
        raise AuthError("Email and password are required.", "VALIDATION_ERROR", 422)

    normalized_email = email.strip().lower()
    user = db.session.query(User).filter_by(email=normalized_email).first()

    generic_error = AuthError(
        "Invalid email or password.", "INVALID_CREDENTIALS", 401
    )

    if user is None:
        # Phase 11: record the attempt even though there's no known
        # user to attach it to — AuditLog.user_id is nullable for
        # exactly this case (see the model's own docstring). We log
        # the email that was tried, not the fact that it doesn't
        # exist as an account, so this can't be used to enumerate
        # registered addresses by reading the audit log either.
        record_audit_log(
            user_id=None,
            action="login_failed",
            resource_type="user",
            description=f"Failed login attempt for {normalized_email}.",
        )
        db.session.commit()
        raise generic_error

    if not verify_password(password, user.password_hash):
        record_audit_log(
            user_id=user.id,
            action="login_failed",
            resource_type="user",
            resource_id=user.id,
            description="Failed login attempt (incorrect password).",
        )
        db.session.commit()
        raise generic_error

    if user.status != AccountStatus.ACTIVE:
        record_audit_log(
            user_id=user.id,
            action="login_failed",
            resource_type="user",
            resource_id=user.id,
            description="Login attempt on a deactivated account.",
        )
        db.session.commit()
        raise AuthError(
            "This account has been deactivated. Contact an administrator.",
            "ACCOUNT_INACTIVE",
            403,
        )

    token = generate_token(user_id=user.id, role=user.role.value)

    record_audit_log(
        user_id=user.id,
        action="login",
        resource_type="user",
        resource_id=user.id,
        description="User logged in.",
    )
    db.session.commit()

    return user, token
