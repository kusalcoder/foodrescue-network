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


from app.utils.geo import geocode_address, is_in_india


def _validate_profile_fields(organization_name, address, city, state, pincode, latitude, longitude):
    error = validate_name(organization_name)
    if error:
        raise ProviderProfileError(error, "VALIDATION_ERROR", 422)

    if not address or not str(address).strip():
        raise ProviderProfileError("Address is required.", "VALIDATION_ERROR", 422)

    if not city or not str(city).strip():
        raise ProviderProfileError("City is required.", "VALIDATION_ERROR", 422)

    if not state or not str(state).strip():
        raise ProviderProfileError("State is required.", "VALIDATION_ERROR", 422)

    if not pincode or not str(pincode).strip():
        raise ProviderProfileError("Pincode is required.", "VALIDATION_ERROR", 422)

    coord_error = validate_coordinates(latitude, longitude)
    if coord_error:
        raise ProviderProfileError(coord_error, "VALIDATION_ERROR", 422)


def create_provider_profile(*, user, data: dict = None) -> ProviderProfile:
    data = data or {}
    if user is None or getattr(user, "role", None) != UserRole.PROVIDER:
        raise ProviderProfileError(
            "Only provider accounts can create a provider profile.",
            "FORBIDDEN",
            403,
        )

    if getattr(user, "provider_profile", None) is not None:
        raise ProviderProfileError(
            "A provider profile already exists for this account. Use update instead.",
            "PROFILE_ALREADY_EXISTS",
            409,
        )

    organization_name = data.get("organization_name")
    address = data.get("address")
    city = data.get("city")
    state = data.get("state")
    pincode = data.get("pincode")
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    _validate_profile_fields(organization_name, address, city, state, pincode, latitude, longitude)

    if latitude is None or longitude is None:
        geo_lat, geo_lng = geocode_address(address, city, state, pincode)
        if geo_lat is not None and geo_lng is not None:
            latitude, longitude = geo_lat, geo_lng

    phone_val = data.get("phone") or data.get("contact_info")
    profile = ProviderProfile(
        user_id=user.id,
        organization_name=organization_name.strip() if isinstance(organization_name, str) else "",
        contact_info=data.get("contact_info") or phone_val,
        phone=phone_val,
        address=address.strip() if isinstance(address, str) else address,
        city=city.strip() if isinstance(city, str) else city,
        state=state.strip() if isinstance(state, str) else state,
        pincode=pincode.strip() if isinstance(pincode, str) else pincode,
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


def update_provider_profile(*, user, data: dict = None) -> ProviderProfile:
    """Update the currently authenticated provider's own profile."""
    data = data or {}
    profile = getattr(user, "provider_profile", None) if user else None
    if profile is None:
        raise ProviderProfileError(
            "No provider profile exists yet for this account. Create one first.",
            "PROFILE_NOT_FOUND",
            404,
        )

    organization_name = data.get("organization_name", profile.organization_name)
    address = data.get("address", profile.address)
    city = data.get("city", profile.city)
    state = data.get("state", profile.state)
    pincode = data.get("pincode", profile.pincode)
    latitude = data.get("latitude", profile.latitude)
    longitude = data.get("longitude", profile.longitude)
    _validate_profile_fields(organization_name, address, city, state, pincode, latitude, longitude)

    if latitude is None or longitude is None or ("address" in data or "city" in data or "state" in data):
        if "latitude" not in data and "longitude" not in data:
            geo_lat, geo_lng = geocode_address(address, city, state, pincode)
            if geo_lat is not None and geo_lng is not None:
                latitude, longitude = geo_lat, geo_lng

    if isinstance(organization_name, str):
        profile.organization_name = organization_name.strip()
    profile.contact_info = data.get("contact_info", profile.contact_info)
    if "phone" in data:
        profile.phone = data.get("phone")
    elif "contact_info" in data and not profile.phone:
        profile.phone = data.get("contact_info")
    if isinstance(address, str):
        profile.address = address.strip()
    if isinstance(city, str):
        profile.city = city.strip()
    if isinstance(state, str):
        profile.state = state.strip()
    if isinstance(pincode, str):
        profile.pincode = pincode.strip()
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
