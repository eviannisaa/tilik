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
#: Every figure here comes from a real source, and naming them is the point:
#: they are checkable, and a reader can go and read them. None of them surveyed
#: this plot. InaRISK models a grid, DIBI records per district, USGS locates
#: epicentres and NCEI records where a wave was observed, so the gap between
#: "the model says moderate here" and "this street floods every February" is a
#: gap only a person standing there can close.
#:
#: The list must stay complete. It named the four hazard sources while the
#: report was also reading elevation, place names, mapped water and places,
#: local news and air quality, so a footer claiming to say where the readings
#: came from named fewer than half of them.
#:
#: One thing here is still unnamed, and deliberately: the flood section falls
#: back to Tilik's own estimate from elevation and distance to water when no
#: mapped zone or InaRISK index answers. That is not a source, so it is not in
#: this list. `FloodInfo.basis` reports it per check, and the section says so.
#: No em dashes. The clause each one carried becomes its own sentence, which
#: reads the same and survives a font or a copy-paste that renders it as a box.
DISCLAIMER = (
    "For reference only. The readings here come from BNPB InaRISK, BNPB's DIBI "
    "disaster archive, the USGS earthquake catalogue, NOAA's tsunami database, "
    "OpenTopography's elevation model, OpenStreetMap's mapped water and places, "
    "Nominatim's place names, Google News for local reporting and the World Air "
    "Quality Index. Those are real sources, but they are national models and "
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
