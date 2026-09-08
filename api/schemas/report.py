"""The composed location report and its assessment."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from api.schemas.common import AssessmentLevel, CamelModel, ConfidenceLevel, DataSource
from api.schemas.location import (
    AirQuality,
    AreaInfo,
    DisasterHistory,
    FloodInfo,
    HazardIndex,
    LocalNews,
    LocationInfo,
    NearbyPlaces,
    TerrainInfo,
)

#: What this report is, and what it is not. Shown in the report footer.
#:
#: Every figure here comes from a real source — BNPB's InaRISK hazard models,
#: BNPB's DIBI disaster archive, the USGS earthquake catalogue, NOAA/NCEI's
#: tsunami database — and naming them is the point: they are checkable, and a
#: reader can go and read them. But all four are *national* products. None of
#: them surveyed this plot. InaRISK models a grid, DIBI records per district,
#: USGS locates epicentres and NCEI records where a wave was observed — so the
#: gap between "the model says moderate here" and "this street floods every
#: February" is a gap only a person standing there can close.
#: No em dashes. The clause each one carried becomes its own sentence, which
#: reads the same and survives a font or a copy-paste that renders it as a box.
DISCLAIMER = (
    "For reference only. The readings here come from BNPB InaRISK, BNPB's DIBI "
    "disaster archive, the USGS earthquake catalogue and NOAA's tsunami "
    "database. Those are real sources, but they are national models and "
    "national records. None of them surveyed this plot. Before you commit, walk "
    "the land yourself and ask the neighbours what happens in the rainy season: "
    "which street floods, how high the water came, what the ground does. That "
    "is knowledge no model holds, and it is worth more than anything on this "
    "page."
)


class AssessmentFactor(CamelModel):
    label: str
    detail: str
    impact: Literal["positive", "neutral", "negative"]


class Assessment(CamelModel):
    level: AssessmentLevel = "unknown"
    headline: str
    factors: list[AssessmentFactor] = Field(default_factory=list)
    confidence: ConfidenceLevel = "none"
    disclaimer: str = DISCLAIMER


class ReportMeta(CamelModel):
    generated_at: str
    sources: list[DataSource] = Field(default_factory=list)
    #: Human-readable names of providers that failed for this request.
    degraded: list[str] = Field(default_factory=list)


class LocationReport(CamelModel):
    location: LocationInfo
    terrain: TerrainInfo
    flood: FloodInfo
    hazards: HazardIndex
    disasters: DisasterHistory
    news: LocalNews
    air_quality: AirQuality
    places: NearbyPlaces
    area: AreaInfo
    assessment: Assessment
    meta: ReportMeta


class HealthResponse(CamelModel):
    status: Literal["ok", "degraded"]
    version: str
    database: Literal["connected", "not_configured", "unavailable"]
    providers: dict[str, str]
