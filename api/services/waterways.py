"""Nearby water features.

PostGIS is preferred when the `waterways` table is populated; otherwise we ask
Overpass (OpenStreetMap) directly. Both are optional — no water data simply
lowers the confidence of the flood section.
"""

from __future__ import annotations

import logging

from api.core.cache import TTLCache
from api.core.config import get_settings
from api.core.errors import TilikError
from api.core.geo import haversine_meters
from api.core.http import fetch_json_from_first
from api.services import overpass
from api.db import repository
from api.schemas.common import DataSource
from api.schemas.location import WaterFeature

logger = logging.getLogger("tilik.services.waterways")

PROVIDER = "overpass"
WATERWAY_KINDS = ("river", "stream", "canal", "drain")

_cache = TTLCache(ttl_seconds=get_settings().cache_ttl_seconds)


def _build_query(latitude: float, longitude: float, radius_meters: int, timeout: int) -> str:
    kinds = "|".join(WATERWAY_KINDS)
    return (
        f"[out:json][timeout:{timeout}];"
        f'way(around:{radius_meters},{latitude},{longitude})["waterway"~"^({kinds})$"];'
        "out tags geom;"
    )


def _nearest_from_elements(
    latitude: float, longitude: float, elements: list[dict]
) -> WaterFeature | None:
    best: WaterFeature | None = None

    for element in elements:
        geometry = element.get("geometry") or []
        if not geometry:
            continue

        distance = min(
            haversine_meters(latitude, longitude, node["lat"], node["lon"])
            for node in geometry
            if "lat" in node and "lon" in node
        )

        if best is None or distance < best.distance_meters:
            tags = element.get("tags") or {}
            best = WaterFeature(
                name=tags.get("name"),
                kind=tags.get("waterway", "waterway"),
                distance_meters=round(distance, 1),
            )

    return best


async def nearest_water(
    latitude: float,
    longitude: float,
    *,
    skip_database: bool = False,
) -> tuple[WaterFeature | None, DataSource]:
    """Closest river/stream/canal, with provenance.

    `skip_database` is set when the caller has already looked in PostGIS, so the
    same query isn't run twice for one report.
    """
    settings = get_settings()
    radius = settings.waterway_radius_meters

    if not skip_database:
        local = await repository.nearest_waterway(latitude, longitude, radius)
        if local is not None:
            return local, DataSource(field="waterways", provider="postgis", quality="database")

    if not settings.enable_external_apis:
        return None, DataSource(
            field="waterways",
            provider="unavailable",
            quality="unavailable",
            note="External APIs are disabled.",
        )

    cache_key = f"water:{latitude:.4f}:{longitude:.4f}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached, DataSource(field="waterways", provider=PROVIDER, quality="live")

    timeout = max(5, int(settings.external_timeout_seconds))
    try:
        # Same host list as the places lookup, for the same reason.
        payload, host_index = await fetch_json_from_first(
            settings.overpass_urls,
            provider=PROVIDER,
            method="POST",
            data=_build_query(latitude, longitude, radius, timeout),
            headers={"Content-Type": "text/plain; charset=utf-8"},
        )
    except TilikError as exc:
        logger.warning("Waterway lookup degraded: %s", exc)
        return None, DataSource(
            field="waterways",
            provider=PROVIDER,
            quality="unavailable",
            note="OpenStreetMap did not answer in time.",
        )

    # Overpass reports a runtime error inside a 200, so the parse has to be able
    # to fail. See `api.services.overpass`.
    try:
        elements = overpass.elements_of(
            payload, provider=PROVIDER, trust_empty=host_index == 0
        )
    except TilikError as exc:
        logger.warning("Waterway lookup degraded: %s", exc)
        return None, DataSource(
            field="waterways",
            provider=PROVIDER,
            quality="unavailable",
            note="OpenStreetMap did not answer in time.",
        )

    nearest = _nearest_from_elements(latitude, longitude, elements)
    _cache.set(cache_key, nearest)

    return nearest, DataSource(field="waterways", provider=PROVIDER, quality="live")
