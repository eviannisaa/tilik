"""Air quality at the nearest monitoring station."""

from __future__ import annotations

from fastapi import APIRouter

from api.routes.dependencies import CoordinatePair
from api.schemas.location import AirQualityResponse
from api.services import air_quality as air_quality_service

router = APIRouter(prefix="/location", tags=["air-quality"])


@router.get("/air-quality", response_model=AirQualityResponse, summary="Air quality")
async def get_air_quality(coordinates: CoordinatePair) -> AirQualityResponse:
    latitude, longitude = coordinates
    air, _ = await air_quality_service.get_air_quality(latitude, longitude)

    return AirQualityResponse(latitude=latitude, longitude=longitude, air_quality=air)
