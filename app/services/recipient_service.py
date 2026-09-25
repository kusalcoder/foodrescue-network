"""
Recipient profile business logic.

Mirrors app/services/provider_service.py closely — a User with
role=RECIPIENT doesn't automatically have a RecipientProfile;
registration (Phase 3) only creates the login identity. This service
handles the separate step of filling in the organization's details
(spec section 7).

Unlike providers, a recipient profile starts with
`verification_status = PENDING` (spec section 7 — "Only authorized
recipient organizations should be able to request food listings").
Verifying a recipient is an administrator action, built in a later
phase alongside the rest of admin user management — this service
only creates/updates the profile data itself.
"""

from app.extensions import db
from app.models import RecipientProfile, UserRole, VerificationStatus
from app.services.notification_service import create_notification
from app.utils.audit import record_audit_log
from app.utils.validation import validate_coordinates, validate_name


class RecipientProfileError(Exception):
    def __init__(self, message: str, error_code: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code


def _validate_profile_fields(organization_name, latitude, longitude):
    error = validate_name(organization_name)
    if error:
        raise RecipientProfileError(error, "VALIDATION_ERROR", 422)

    coord_error = validate_coordinates(latitude, longitude)
    if coord_error:
        raise RecipientProfileError(coord_error, "VALIDATION_ERROR", 422)


def create_recipient_profile(*, user, data: dict) -> RecipientProfile:
    if user.role != UserRole.RECIPIENT:
        raise RecipientProfileError(
            "Only recipient accounts can create a recipient profile.",
            "FORBIDDEN",
            403,
        )

    if user.recipient_profile is not None:
        raise RecipientProfileError(
            "A recipient profile already exists for this account. Use update instead.",
            "PROFILE_ALREADY_EXISTS",
            409,
        )

    organization_name = data.get("organization_name")
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    _validate_profile_fields(organization_name, latitude, longitude)

    profile = RecipientProfile(
        user_id=user.id,
        organization_name=organization_name.strip(),
        contact_info=data.get("contact_info"),
        address=data.get("address"),
        city=data.get("city"),
        latitude=latitude,
        longitude=longitude,
        description=data.get("description"),
    )
    db.session.add(profile)
    db.session.flush()

    record_audit_log(
        user_id=user.id,
        action="recipient_profile_created",
        resource_type="recipient_profile",
        resource_id=profile.id,
        description=f"Recipient profile created for {profile.organization_name!r}. "
        "Pending verification.",
    )
    db.session.commit()
    return profile


def update_recipient_profile(*, user, data: dict) -> RecipientProfile:
    profile = user.recipient_profile
    if profile is None:
        raise RecipientProfileError(
            "No recipient profile exists yet for this account. Create one first.",
            "PROFILE_NOT_FOUND",
            404,
        )

    organization_name = data.get("organization_name", profile.organization_name)
    latitude = data.get("latitude", profile.latitude)
    longitude = data.get("longitude", profile.longitude)
    _validate_profile_fields(organization_name, latitude, longitude)

    profile.organization_name = organization_name.strip()
    profile.contact_info = data.get("contact_info", profile.contact_info)
    profile.address = data.get("address", profile.address)
    profile.city = data.get("city", profile.city)
    profile.latitude = latitude
    profile.longitude = longitude
    profile.description = data.get("description", profile.description)

    record_audit_log(
        user_id=user.id,
        action="recipient_profile_updated",
        resource_type="recipient_profile",
        resource_id=profile.id,
        description="Recipient profile updated.",
    )
    db.session.commit()
    return profile


def verify_recipient_profile(*, profile_id: int, admin_user_id: int) -> RecipientProfile:
    """
    Administrator action: mark a recipient organization as verified.

    This is pulled forward from the full Administrator module (built
    later, alongside broader user/account management) because the
    request workflow (Phase 6) depends on it: spec section 7 requires
    that "only authorized recipient organizations" can place requests,
    so there needs to be *some* way to flip that flag before Phase 6
    can be meaningfully tested end-to-end.
    """
    profile = db.session.get(RecipientProfile, profile_id)
    if profile is None:
        raise RecipientProfileError(
            "Recipient profile not found.", "PROFILE_NOT_FOUND", 404
        )

    profile.verification_status = VerificationStatus.VERIFIED

    record_audit_log(
        user_id=admin_user_id,
        action="recipient_verified",
        resource_type="recipient_profile",
        resource_id=profile.id,
        description=f"Recipient profile {profile.id} verified by administrator.",
    )
    create_notification(
        user_id=profile.user_id,
        notification_type="recipient_verified",
        title="Your organization is verified",
        message=f"{profile.organization_name!r} has been verified. "
        "You can now request food listings.",
        related_resource_type="recipient_profile",
        related_resource_id=profile.id,
    )
    db.session.commit()
    return profile
