"""
Provider profile business logic.

A User with role=PROVIDER doesn't automatically have a
ProviderProfile — registration (Phase 3) only creates the login
identity. This service handles the separate step of filling in the
organization's details (spec section 6), kept independent so a
provider can register and log in immediately, then complete their
profile afterward.
"""

from app.extensions import db
from app.models import ProviderProfile, UserRole
from app.utils.audit import record_audit_log
from app.utils.validation import validate_coordinates, validate_name


class ProviderProfileError(Exception):
    def __init__(self, message: str, error_code: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code


def _validate_profile_fields(organization_name, latitude, longitude):
    error = validate_name(organization_name)
    if error:
        raise ProviderProfileError(error, "VALIDATION_ERROR", 422)

    coord_error = validate_coordinates(latitude, longitude)
    if coord_error:
        raise ProviderProfileError(coord_error, "VALIDATION_ERROR", 422)


def create_provider_profile(*, user, data: dict) -> ProviderProfile:
    """
    Create the provider profile for the currently authenticated user.

    Raises ProviderProfileError if the user already has a profile
    (this is a one-time "complete my profile" action; further changes
    go through `update_provider_profile`), or if the user isn't
    actually a PROVIDER.
    """
    if user.role != UserRole.PROVIDER:
        raise ProviderProfileError(
            "Only provider accounts can create a provider profile.",
            "FORBIDDEN",
            403,
        )

    if user.provider_profile is not None:
        raise ProviderProfileError(
            "A provider profile already exists for this account. Use update instead.",
            "PROFILE_ALREADY_EXISTS",
            409,
        )

    organization_name = data.get("organization_name")
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    _validate_profile_fields(organization_name, latitude, longitude)

    profile = ProviderProfile(
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
        action="provider_profile_created",
        resource_type="provider_profile",
        resource_id=profile.id,
        description=f"Provider profile created for {profile.organization_name!r}.",
    )
    db.session.commit()
    return profile


def update_provider_profile(*, user, data: dict) -> ProviderProfile:
    """Update the currently authenticated provider's own profile."""
    profile = user.provider_profile
    if profile is None:
        raise ProviderProfileError(
            "No provider profile exists yet for this account. Create one first.",
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
        action="provider_profile_updated",
        resource_type="provider_profile",
        resource_id=profile.id,
        description="Provider profile updated.",
    )
    db.session.commit()
    return profile
