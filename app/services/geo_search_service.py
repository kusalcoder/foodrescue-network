"""
Cross-profile location search — Phase 8.

Two directions, both from the README's Phase 8 preview:
    - a Provider finding the nearest VERIFIED recipient organizations
      (e.g. to proactively reach out about a big surplus)
    - a Recipient finding the nearest Providers that currently have
      at least one AVAILABLE listing

Both reuse the same Haversine distance helper as listing search
(app/services/listing_service.browse_listings_within_radius), but the
underlying query shape is different enough — profile-to-profile, no
FoodListing status/category filters or pagination to reuse — that it
gets its own small service module rather than being bolted onto
listing_service.py.
"""

import math

from app.extensions import db
from app.models import (
    FoodListing,
    ListingStatus,
    ProviderProfile,
    RecipientProfile,
    VerificationStatus,
)
from app.utils.geo import haversine_km


def _paginate_scored(scored: list, page: int, limit: int):
    """Sort (item, distance_km) pairs nearest-first and paginate in
    Python, mirroring app.utils.pagination's metadata shape."""
    scored.sort(key=lambda pair: pair[1])

    total = len(scored)
    total_pages = math.ceil(total / limit) if total else 0
    start = (page - 1) * limit
    page_items = scored[start : start + limit]

    metadata = {"page": page, "limit": limit, "total": total, "total_pages": total_pages}
    return page_items, metadata


def nearest_verified_recipients(
    *, near_lat: float, near_lng: float, radius_km: float, page: int, limit: int
):
    """
    Verified recipient organizations within radius_km of
    (near_lat, near_lng), nearest first. Intended for a provider
    deciding who to reach out to about a listing.

    Returns (page_items, pagination_metadata) where each page item is
    a (RecipientProfile, distance_km) tuple.
    """
    candidates = (
        db.session.query(RecipientProfile)
        .filter(RecipientProfile.verification_status == VerificationStatus.VERIFIED)
        .filter(RecipientProfile.latitude.isnot(None))
        .filter(RecipientProfile.longitude.isnot(None))
        .all()
    )

    scored = []
    for profile in candidates:
        distance_km = haversine_km(
            near_lat, near_lng, float(profile.latitude), float(profile.longitude)
        )
        if distance_km <= radius_km:
            scored.append((profile, distance_km))

    return _paginate_scored(scored, page, limit)


def nearest_providers_with_availability(
    *, near_lat: float, near_lng: float, radius_km: float, page: int, limit: int
):
    """
    Providers within radius_km of (near_lat, near_lng) who currently
    have at least one AVAILABLE listing, nearest first. Intended for
    a recipient looking for who has food available nearby right now.

    Returns (page_items, pagination_metadata) where each page item is
    a (ProviderProfile, distance_km) tuple.
    """
    candidates = (
        db.session.query(ProviderProfile)
        .join(FoodListing, FoodListing.provider_id == ProviderProfile.id)
        .filter(FoodListing.status == ListingStatus.AVAILABLE)
        .filter(ProviderProfile.latitude.isnot(None))
        .filter(ProviderProfile.longitude.isnot(None))
        .distinct()
        .all()
    )

    scored = []
    for profile in candidates:
        distance_km = haversine_km(
            near_lat, near_lng, float(profile.latitude), float(profile.longitude)
        )
        if distance_km <= radius_km:
            scored.append((profile, distance_km))

    return _paginate_scored(scored, page, limit)
