"""Shared route dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Query

from api.core.geo import validate_coordinates

LatQuery = Annotated[
    float,
    Query(ge=-90, le=90, description="Latitude in decimal degrees (WGS 84)."),
]
LngQuery = Annotated[
    float,
    Query(ge=-180, le=180, description="Longitude in decimal degrees (WGS 84)."),
]


async def coordinate_pair(lat: LatQuery, lng: LngQuery) -> tuple[float, float]:
    """Validate and round `lat`/`lng` once, for every endpoint that takes them."""
    return validate_coordinates(lat, lng)


CoordinatePair = Annotated[tuple[float, float], Depends(coordinate_pair)]
