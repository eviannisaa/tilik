"""Coordinate helpers used across services.

Distances here are great-circle approximations — good to a few metres at the
scales this app cares about, and cheap enough to run without PostGIS.
"""

from __future__ import annotations

import math

from api.core.errors import InvalidCoordinatesError

EARTH_RADIUS_M = 6_371_008.8


def validate_coordinates(latitude: float, longitude: float) -> tuple[float, float]:
    """Reject anything off-planet or non-finite before it reaches a provider."""
    if not math.isfinite(latitude) or not math.isfinite(longitude):
        raise InvalidCoordinatesError()
    if not -90.0 <= latitude <= 90.0 or not -180.0 <= longitude <= 180.0:
        raise InvalidCoordinatesError()
    return round(latitude, 6), round(longitude, 6)


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)

    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def parse_coordinate_pair(text: str) -> tuple[float, float] | None:
    """Read `-6.9175, 107.6191` typed straight into the search box."""
    parts = [part.strip() for part in text.replace(";", ",").split(",")]
    if len(parts) != 2:
        return None
    try:
        latitude, longitude = float(parts[0]), float(parts[1])
    except ValueError:
        return None
    if not -90.0 <= latitude <= 90.0 or not -180.0 <= longitude <= 180.0:
        return None
    return latitude, longitude
