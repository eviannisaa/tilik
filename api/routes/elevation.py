"""Elevation and terrain for a single point."""

from __future__ import annotations

from fastapi import APIRouter

from api.routes.dependencies import CoordinatePair
from api.schemas.location import ElevationResponse
from api.services import elevation as elevation_service

router = APIRouter(prefix="/location", tags=["terrain"])


@router.get("/elevation", response_model=ElevationResponse, summary="Elevation at a point")
async def get_elevation(coordinates: CoordinatePair) -> ElevationResponse:
    latitude, longitude = coordinates
    terrain, source = await elevation_service.get_terrain(latitude, longitude)

    return ElevationResponse(
        latitude=latitude,
        longitude=longitude,
        terrain=terrain,
        provider=source.provider,
    )
