"""Place search and reverse geocoding."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from api.core.errors import LocationNotFoundError
from api.routes.dependencies import CoordinatePair
from api.schemas.location import SearchResponse, SearchResult
from api.services import geocoding

router = APIRouter(prefix="/location", tags=["location"])


@router.get("/search", response_model=SearchResponse, summary="Search for a place")
async def search_locations(
    q: Annotated[str, Query(min_length=2, max_length=200, description="Place name or address.")],
    limit: Annotated[int, Query(ge=1, le=20)] = 6,
) -> SearchResponse:
    results, provider, degraded = await geocoding.search(q, limit)
    return SearchResponse(query=q, results=results, provider=provider, degraded=degraded)


@router.get("/reverse", response_model=SearchResponse, summary="Name a coordinate")
async def reverse_geocode(coordinates: CoordinatePair) -> SearchResponse:
    latitude, longitude = coordinates
    location = await geocoding.reverse(latitude, longitude)

    if location is None:
        raise LocationNotFoundError("We couldn't find a place name for that point.")

    return SearchResponse(
        query=f"{latitude},{longitude}",
        results=[
            SearchResult(
                latitude=latitude,
                longitude=longitude,
                name=location.name or "Unnamed place",
                display_name=location.display_name or "",
                category="reverse",
                # Passed through rather than dropped: the caller needs to know
                # which kecamatan, kabupaten and province the point sits in.
                district=location.district,
                city=location.city,
                province=location.province,
            )
        ],
        provider="nominatim",
    )
