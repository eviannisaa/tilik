"""Facilities near a point, from OpenStreetMap."""

from __future__ import annotations

from fastapi import APIRouter

from api.routes.dependencies import CoordinatePair
from api.schemas.location import PlacesResponse
from api.services import places as places_service

router = APIRouter(prefix="/location", tags=["places"])


@router.get("/places", response_model=PlacesResponse, summary="What's nearby")
async def get_places(coordinates: CoordinatePair) -> PlacesResponse:
    latitude, longitude = coordinates
    places, _ = await places_service.get_nearby_places(latitude, longitude)

    return PlacesResponse(latitude=latitude, longitude=longitude, places=places)
