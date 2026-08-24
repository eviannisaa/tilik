"""The composed location report — the endpoint the UI actually calls."""

from __future__ import annotations

from fastapi import APIRouter

from api.routes.dependencies import CoordinatePair
from api.schemas.report import LocationReport
from api.services import report as report_service

router = APIRouter(prefix="/location", tags=["report"])


@router.get("/report", response_model=LocationReport, summary="Full location report")
async def get_report(coordinates: CoordinatePair) -> LocationReport:
    latitude, longitude = coordinates
    return await report_service.build_report(latitude, longitude)
