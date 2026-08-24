"""Disaster history and flood risk for a single point."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter

from api.routes.dependencies import CoordinatePair
from api.schemas.location import DisastersResponse, FloodRiskResponse
from api.services import disasters as disaster_service
from api.services import elevation as elevation_service
from api.services import flood as flood_service
from api.services import inarisk

router = APIRouter(prefix="/location", tags=["hazards"])


@router.get("/disasters", response_model=DisastersResponse, summary="Nearby disaster history")
async def get_disasters(coordinates: CoordinatePair) -> DisastersResponse:
    latitude, longitude = coordinates
    history, _ = await disaster_service.get_disaster_history(latitude, longitude)

    return DisastersResponse(latitude=latitude, longitude=longitude, disasters=history)


@router.get("/flood-risk", response_model=FloodRiskResponse, summary="Flood risk at a point")
async def get_flood_risk(coordinates: CoordinatePair) -> FloodRiskResponse:
    latitude, longitude = coordinates

    # Flood risk reads both elevation and BNPB's flood-hazard index. Fetch the
    # same inputs the full report uses, so the two endpoints can't disagree
    # about the same coordinate.
    terrain_result, hazards = await asyncio.gather(
        elevation_service.get_terrain(latitude, longitude),
        inarisk.get_hazards(latitude, longitude, keys=("flood",)),
    )
    terrain, _ = terrain_result

    flood, _ = await flood_service.assess_flood_risk(
        latitude, longitude, terrain, hazards.get("flood")
    )

    return FloodRiskResponse(latitude=latitude, longitude=longitude, flood=flood)
