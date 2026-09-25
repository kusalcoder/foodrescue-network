"""
Geo utilities — Phase 8 (Location-Based Search).

Distance is computed with the Haversine formula, which is accurate
enough for city/regional-scale food-rescue logistics without pulling
in a PostGIS extension or an external geocoding service. Every
distance this module returns is in kilometers.
"""

import math

EARTH_RADIUS_KM = 6371.0088

DEFAULT_RADIUS_KM = 25.0
MAX_RADIUS_KM = 500.0


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """
    Great-circle distance between two (lat, lon) points, in km.
    All four arguments must already be plain floats.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c


def validate_lat_lng(latitude, longitude, *, field_prefix="near"):
    """
    Both <prefix>_lat and <prefix>_lng must be supplied together and
    be valid coordinates. Returns an error message string, or None
    if the pair is valid (or both are simply absent).
    """
    if latitude is None and longitude is None:
        return None

    if latitude is None or longitude is None:
        return (
            f"Both {field_prefix}_lat and {field_prefix}_lng must be "
            "provided together."
        )

    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return f"{field_prefix}_lat and {field_prefix}_lng must be numbers."

    if not (-90 <= lat <= 90):
        return f"{field_prefix}_lat must be between -90 and 90."
    if not (-180 <= lon <= 180):
        return f"{field_prefix}_lng must be between -180 and 180."
    return None


def validate_radius_km(value, default=DEFAULT_RADIUS_KM, maximum=MAX_RADIUS_KM):
    """
    Parse a `radius_km` query parameter.

    Returns (radius, error) — falls back to `default` when the value
    is absent, but treats an out-of-range or non-numeric value as a
    validation error rather than silently clamping it, so callers get
    clear feedback instead of a quietly "wrong" search.
    """
    if value is None:
        return default, None
    try:
        radius = float(value)
    except (TypeError, ValueError):
        return None, "radius_km must be a number."
    if radius <= 0:
        return None, "radius_km must be greater than zero."
    if radius > maximum:
        return None, f"radius_km must be {maximum:g} or less."
    return radius, None
