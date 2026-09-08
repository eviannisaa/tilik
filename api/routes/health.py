"""Service health, including whether the optional database is reachable."""

from __future__ import annotations

from fastapi import APIRouter

from api.core.config import get_settings
from api.db import database_status
from api.schemas.report import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Service health")
async def health() -> HealthResponse:
    settings = get_settings()
    database = await database_status()

    return HealthResponse(
        # A missing database is a supported configuration, not a failure.
        status="degraded" if database == "unavailable" else "ok",
        version=settings.version,
        database=database,
        providers={
            "geocoding": settings.nominatim_base_url,
            "elevation": (
                settings.opentopography_api_url
                if settings.opentopography_api_key
                else f"{settings.elevation_api_url} (OpenTopography key not set)"
            ),
            "hazards": settings.inarisk_base_url,
            "earthquakes": settings.earthquake_api_url,
            "features": settings.overpass_api_url,
            "airQuality": (
                settings.waqi_api_url
                if settings.waqi_api_token
                else f"{settings.waqi_api_url} (WAQI token not set)"
            ),
            "disasterFeed": settings.disaster_api_url or "not_configured",
            "externalApis": "enabled" if settings.enable_external_apis else "disabled",
        },
    )
