"""Composes the full location report.

Independent lookups run concurrently; flood risk waits on terrain because it
reads elevation. Any single provider failing degrades one section rather than
failing the request.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from api.core.config import get_settings
from api.core.geo import validate_coordinates
from api.db import repository
from api.schemas.common import DataQuality, DataSource
from api.schemas.location import (
    AreaFeature,
    AreaInfo,
    Coordinates,
    HazardIndex,
    LocalNews,
    LocationInfo,
)
from api.schemas.report import LocationReport, ReportMeta
from api.services import assessment as assessment_service
from api.services import disasters as disaster_service
from api.services import elevation as elevation_service
from api.services import flood as flood_service
from api.services import geocoding, inarisk
from api.services import news as news_service
from api.services import places as places_service

#: Provider keys mapped to names a user would recognise in the UI.
FRIENDLY_PROVIDER_NAMES = {
    "opentopodata": "the elevation service",
    "overpass": "OpenStreetMap",
    "nominatim": "the place-name service",
    "USGS": "the earthquake catalogue",
    "postgis": "our spatial database",
    "heuristic": "our flood model",
    "inarisk": "BNPB InaRISK",
    "opentopography": "OpenTopography",
    "google-news": "the news feed",
}

#: Fallback wording when we don't even know which provider was meant to answer.
FRIENDLY_FIELD_NAMES = {
    "location": "place names",
    "elevation": "elevation data",
    "waterways": "waterway data",
    "flood": "flood data",
    "disasters": "disaster records",
    "places": "nearby places",
    "hazards": "BNPB hazard indices",
    "news": "local news",
}


def _build_area(
    latitude: float,
    longitude: float,
    location: LocationInfo,
    nearby: list[AreaFeature],
) -> AreaInfo:
    administrative = ", ".join(
        part
        for part in (location.district or location.locality, location.city, location.province)
        if part
    )

    return AreaInfo(
        administrative_area=administrative or None,
        country=location.country,
        coordinates=Coordinates(latitude=latitude, longitude=longitude),
        nearby_features=nearby,
    )


def _hazard_source(hazards: HazardIndex) -> DataSource:
    """Provenance for the InaRISK section, based on what actually answered."""
    answered = [reading for reading in hazards.readings if reading.status == "ok"]
    reachable = any(reading.status != "unavailable" for reading in hazards.readings)
    ingested = [reading for reading in answered if reading.source == "postgis"]

    if answered:
        # Ingested cells are the same BNPB model, just read locally.
        from_db = len(ingested) == len(answered)
        return DataSource(
            field="hazards",
            provider="postgis" if from_db else "inarisk",
            quality="database" if from_db else "live",
            note=(
                None
                if not ingested or from_db
                else f"{len(ingested)} of {len(answered)} layers came from ingested data."
            ),
        )

    quality: DataQuality = "live" if reachable else "unavailable"
    note = (
        "InaRISK answered but models no hazard at this point."
        if reachable
        else "BNPB InaRISK did not answer."
    )
    return DataSource(field="hazards", provider="inarisk", quality=quality, note=note)


def _degraded_names(sources: list[DataSource]) -> list[str]:
    """Name what the user is missing, in words they'd recognise."""
    names: list[str] = []
    for source in sources:
        if source.quality != "unavailable":
            continue

        friendly = FRIENDLY_PROVIDER_NAMES.get(source.provider)
        if friendly is None:
            # An unnamed provider tells the user nothing; describe the gap instead.
            friendly = FRIENDLY_FIELD_NAMES.get(source.field, source.field)

        if friendly not in names:
            names.append(friendly)
    return names


async def build_report(latitude: float, longitude: float) -> LocationReport:
    """Gather every section for one point and fold it into a single response."""
    latitude, longitude = validate_coordinates(latitude, longitude)

    settings = get_settings()

    # Ask PostGIS everything it can answer in one query: ingested InaRISK
    # hazards, mapped flood zones, nearest waterway, a sampled elevation and
    # disaster events in range. `None` means no database (or an unusable one),
    # in which case each service falls back to its external provider.
    analysis = await repository.analyse_location(
        latitude,
        longitude,
        waterway_radius_meters=settings.waterway_radius_meters,
        disaster_radius_meters=settings.disaster_radius_meters,
        disaster_years=settings.disaster_years,
        event_limit=disaster_service.STORED_FETCH_LIMIT,
        event_per_area=disaster_service.MAX_EVENTS_PER_AREA,
        hazard_radius_meters=settings.inarisk_neighbourhood_meters,
    )
    local = analysis or repository.LocalAnalysis()
    # True once PostGIS has answered, so services don't re-run the same reads.
    queried_locally = analysis is not None

    # News is the one lookup with a dependency: it searches by place name, so it
    # has nothing to ask for until geocoding answers. Chaining it behind its own
    # task rather than awaiting it after the gather keeps it inside the same
    # window as InaRISK, which is what the report actually waits on.
    geocode_task = asyncio.ensure_future(geocoding.reverse(latitude, longitude))

    async def _news_for_geocode() -> tuple[LocalNews, DataSource]:
        resolved = await asyncio.shield(geocode_task)
        return await news_service.get_local_news(
            resolved or LocationInfo(latitude=latitude, longitude=longitude)
        )

    # None of these depend on each other, so the report costs the slowest one
    # rather than the sum. InaRISK is usually that one — unless it's ingested.
    (
        location_result,
        terrain_result,
        disaster_result,
        hazard_readings,
        places_result,
        news_result,
    ) = (
        await asyncio.gather(
            geocode_task,
            elevation_service.get_terrain(latitude, longitude, local_elevation=local.elevation),
            disaster_service.get_disaster_history(
                latitude,
                longitude,
                local_events=local.disasters,
                skip_database=queried_locally,
            ),
            inarisk.get_hazards(
                latitude,
                longitude,
                local=local.hazards or None,
                covered=local.covered_hazards if queried_locally else None,
            ),
            places_service.get_nearby_places(latitude, longitude),
            _news_for_geocode(),
        )
    )

    terrain, terrain_source = terrain_result
    disasters, disaster_sources = disaster_result
    places, places_source = places_result
    hazards = inarisk.build_hazard_index(hazard_readings)

    # Flood risk reads both the elevation and BNPB's flood index, so it resolves
    # last — but off already-fetched data, not another round trip.
    flood, flood_sources = await flood_service.assess_flood_risk(
        latitude,
        longitude,
        terrain,
        hazard_readings.get("flood"),
        local_zone=local.flood_zone,
        local_water=local.nearest_water,
        skip_local_queries=queried_locally,
    )

    location = location_result or LocationInfo(latitude=latitude, longitude=longitude)
    local_news, news_source = news_result

    location_source = DataSource(
        field="location",
        provider="nominatim" if location_result else "unavailable",
        quality="live" if location_result else "unavailable",
        note=None if location_result else "No place name could be resolved for this point.",
    )

    nearby: list[AreaFeature] = []
    if flood.nearest_river is not None:
        nearby.append(
            AreaFeature(
                name=flood.nearest_river.name or flood.nearest_river.kind.title(),
                kind=flood.nearest_river.kind,
                distance_meters=flood.nearest_river.distance_meters,
            )
        )

    sources = [
        location_source,
        terrain_source,
        *flood_sources,
        _hazard_source(hazards),
        *disaster_sources,
        news_source,
        places_source,
    ]

    return LocationReport(
        location=location,
        terrain=terrain,
        flood=flood,
        hazards=hazards,
        disasters=disasters,
        news=local_news,
        places=places,
        area=_build_area(latitude, longitude, location, nearby),
        assessment=assessment_service.build_assessment(
            terrain, flood, disasters, hazards, places
        ),
        meta=ReportMeta(
            generated_at=datetime.now(UTC).isoformat(),
            sources=sources,
            degraded=_degraded_names(sources),
        ),
    )
