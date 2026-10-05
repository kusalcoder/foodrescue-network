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


# --- India Geographical Boundaries & Fallback Constants ---
INDIA_LAT_MIN = 6.5
INDIA_LAT_MAX = 37.5
INDIA_LNG_MIN = 68.0
INDIA_LNG_MAX = 97.5

DEFAULT_INDIA_LAT = 28.6139
DEFAULT_INDIA_LNG = 77.2090
DEFAULT_INDIA_CITY = "New Delhi"


def is_in_india(latitude, longitude) -> bool:
    """Return True if (latitude, longitude) falls within India's geographical bounding box."""
    if latitude is None or longitude is None:
        return False
    try:
        lat = float(latitude)
        lng = float(longitude)
        return (INDIA_LAT_MIN <= lat <= INDIA_LAT_MAX) and (INDIA_LNG_MIN <= lng <= INDIA_LNG_MAX)
    except (TypeError, ValueError):
        return False


def validate_india_location(latitude, longitude, country=None, address=None) -> str | None:
    """
    Validation helper to enforce that donations/locations remain strictly within India.
    Returns an error message string if outside India, or None if valid.
    """
    if country and isinstance(country, str):
        c_clean = country.strip().lower()
        if c_clean not in ["india", "in", "bharat", ""]:
            return "Donations can only be created within India. Overseas locations are not allowed."

    if address and isinstance(address, str):
        addr_lower = address.lower()
        foreign_keywords = [
            "united states", "usa", "u.s.a", "canada", "united kingdom", "uk", "u.k.",
            "australia", "germany", "france", "singapore", "united arab emirates", "uae",
            "china", "japan", "brazil", "russia", "pakistan", "bangladesh", "sri lanka", "nepal"
        ]
        for kw in foreign_keywords:
            if f", {kw}" in addr_lower or f" {kw}" in addr_lower or addr_lower.endswith(kw):
                return f"Donations can only be created within India. Location '{address}' appears to be outside India."

    if latitude is not None and longitude is not None:
        if not is_in_india(latitude, longitude):
            return "Donations can only be created within India. Coordinates fall outside India."

    return None


KNOWN_INDIAN_CITIES_COORDS = {
    "vijayawada": (16.5062, 80.6480),
    "hyderabad": (17.3850, 78.4867),
    "visakhapatnam": (17.6868, 83.2185),
    "guntur": (16.3067, 80.4365),
    "tirupati": (13.6288, 79.4192),
    "warangal": (17.9689, 79.5941),
    "kakinada": (16.9891, 82.2475),
    "nellore": (14.4426, 79.9865),
    "kurnool": (15.8281, 78.0373),
    "chennai": (13.0827, 80.2707),
    "bengaluru": (12.9716, 77.5946),
    "bangalore": (12.9716, 77.5946),
    "mumbai": (19.0760, 72.8777),
    "pune": (18.5204, 73.8567),
    "delhi": (28.6139, 77.2090),
    "new delhi": (28.6139, 77.2090),
    "kolkata": (22.5726, 88.3639),
    "ahmedabad": (23.0225, 72.5714),
    "jaipur": (26.9124, 75.7873),
    "lucknow": (26.8467, 80.9462),
}


def geocode_address(address: str, city: str, state: str, pincode: str = None) -> tuple[float | None, float | None]:
    """
    Geocode an Indian address string into (latitude, longitude) coordinates.
    Checks known Indian city coordinates first for instant resolution,
    then attempts OpenStreetMap Nominatim if needed.
    Returns (lat, lng) or (None, None) if resolution fails.
    """
    import json
    import urllib.parse
    import urllib.request

    if city and isinstance(city, str):
        city_key = city.strip().lower()
        if city_key in KNOWN_INDIAN_CITIES_COORDS:
            return KNOWN_INDIAN_CITIES_COORDS[city_key]

    import os
    if os.environ.get("FLASK_ENV") == "testing":
        return None, None

    query_str = ", ".join(parts)
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
        "format": "json",
        "q": query_str,
        "limit": 1
    })
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "FoodRescueNetwork/1.0 (contact@foodrescue.org)"}
    )

    try:
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                if data and len(data) > 0:
                    lat = float(data[0]["lat"])
                    lng = float(data[0]["lon"])
                    if is_in_india(lat, lng):
                        return lat, lng
    except Exception:
        pass

    return None, None


