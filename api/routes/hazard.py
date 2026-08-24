"""BNPB InaRISK multi-hazard indices for a single point."""

from __future__ import annotations

from fastapi import APIRouter

from api.routes.dependencies import CoordinatePair
from api.schemas.location import HazardsResponse
from api.services import inarisk

router = APIRouter(prefix="/location", tags=["hazards"])


@router.get("/hazards", response_model=HazardsResponse, summary="InaRISK hazard indices")
async def get_hazards(coordinates: CoordinatePair) -> HazardsResponse:
    latitude, longitude = coordinates
    readings = await inarisk.get_hazards(latitude, longitude)

    return HazardsResponse(
        latitude=latitude,
        longitude=longitude,
        hazards=inarisk.build_hazard_index(readings),
    )
