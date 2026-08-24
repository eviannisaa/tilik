"""Elevation and terrain classification.

Any provider returning ``{"results": [{"elevation": <metres>}]}`` works —
OpenTopoData and Open-Elevation both do. Point `ELEVATION_API_URL` elsewhere to
swap it.
"""

from __future__ import annotations

import logging
from hashlib import blake2b

from api.core.cache import TTLCache
from api.core.config import get_settings
from api.core.errors import TilikError
from api.core.http import fetch_json
from api.db import repository
from api.schemas.common import DataSource, TerrainKind
from api.schemas.location import TerrainInfo
from api.services import opentopography

logger = logging.getLogger("tilik.services.elevation")

#: Key-less fallback provider, used when OpenTopography isn't configured.
PROVIDER = "opentopodata"
#: Sampled points further away than this tell you little in hilly ground.
DB_SAMPLE_RADIUS_M = 150

_cache = TTLCache(ttl_seconds=get_settings().cache_ttl_seconds)


def classify_terrain(elevation: float | None) -> TerrainKind:
    if elevation is None:
        return "unknown"
    if elevation < 10:
        return "coastal"
    if elevation < 100:
        return "lowland"
    if elevation < 400:
        return "hilly"
    if elevation < 1000:
        return "highland"
    return "mountainous"


def describe_terrain(elevation: float | None, terrain: TerrainKind) -> str:
    if elevation is None:
        return (
            "We couldn't get an elevation reading for this point, so the terrain "
            "here is unknown. Everything else in this report still applies."
        )

    height = f"{round(elevation)} m above sea level"
    match terrain:
        case "coastal":
            return (
                f"At {height}, this sits barely above the sea. Ground this low is "
                "exposed to tidal flooding and storm surge."
            )
        case "lowland":
            return (
                f"At {height}, this is flat lowland. That is typical for cities and "
                "farmland, "
                "and where water tends to collect during heavy rain."
            )
        case "hilly":
            return (
                f"At {height}, the ground is elevated and rolling. Water drains "
                "away more easily here."
            )
        case "highland":
            return (
                f"At {height}, this is highland. Flooding is less of a concern, but "
                "slope stability and access roads usually are."
            )
        case "mountainous":
            return (
                f"At {height}, this is mountainous ground. Expect steep slopes, "
                "landslide exposure, and harder construction access."
            )
        case _:
            return f"This point sits at {height}."


def _sample_elevation(latitude: float, longitude: float) -> float:
    """Deterministic stand-in used only when external APIs are switched off."""
    seed = blake2b(f"{latitude:.4f},{longitude:.4f}".encode(), digest_size=4).digest()
    return round(int.from_bytes(seed, "big") % 900 / 1.0, 1)


async def _fetch_opentopodata(latitude: float, longitude: float) -> float | None:
    """Key-less fallback: any `{"results": [{"elevation": ...}]}` endpoint."""
    settings = get_settings()
    payload = await fetch_json(
        settings.elevation_api_url,
        provider=PROVIDER,
        params={"locations": f"{latitude},{longitude}"},
    )

    if not isinstance(payload, dict):
        return None
    results = payload.get("results") or []
    if not results:
        return None

    elevation = results[0].get("elevation")
    return float(elevation) if elevation is not None else None


async def _fetch_remote_elevation(latitude: float, longitude: float) -> tuple[float | None, str]:
    """Ask OpenTopography first, then the key-less provider.

    Returns ``(elevation, provider)`` so the report can name its real source.
    """
    if opentopography.is_configured():
        try:
            elevation = await opentopography.get_elevation(latitude, longitude)
            if elevation is not None:
                return elevation, opentopography.PROVIDER
            logger.info("OpenTopography had no data for %s,%s", latitude, longitude)
        except TilikError as exc:
            # A dead or over-quota key shouldn't cost the user their reading.
            logger.warning("OpenTopography unavailable, falling back: %s", exc)

    return await _fetch_opentopodata(latitude, longitude), PROVIDER


async def get_terrain(
    latitude: float,
    longitude: float,
    *,
    local_elevation: float | None = None,
) -> tuple[TerrainInfo, DataSource]:
    """Best available elevation for a point, plus where it came from.

    `local_elevation` lets a caller pass a value already read from PostGIS,
    so a report doesn't query the database twice for the same point.
    """
    cache_key = f"elev:{latitude:.4f}:{longitude:.4f}"
    settings = get_settings()

    if not settings.enable_external_apis:
        elevation = _sample_elevation(latitude, longitude)
        terrain = classify_terrain(elevation)
        return (
            TerrainInfo(
                elevation=elevation,
                terrain=terrain,
                description=describe_terrain(elevation, terrain),
                confidence="low",
            ),
            DataSource(
                field="elevation",
                provider="sample-data",
                quality="estimate",
                note="External APIs are disabled, so this is placeholder data.",
            ),
        )

    cached = _cache.get(cache_key)
    if cached is not None:
        elevation, provider, quality = cached
    else:
        elevation, provider, quality = None, PROVIDER, "unavailable"

        # A stored sample right next to the point beats a network round trip.
        local = local_elevation
        if local is None:
            local = await repository.nearest_elevation(latitude, longitude, DB_SAMPLE_RADIUS_M)
        if local is not None:
            elevation, provider, quality = local, "postgis", "database"
        else:
            try:
                elevation, provider = await _fetch_remote_elevation(latitude, longitude)
                quality = "live" if elevation is not None else "unavailable"
            except TilikError as exc:
                logger.warning("Elevation lookup degraded: %s", exc)

        if elevation is not None:
            _cache.set(cache_key, (elevation, provider, quality))

    terrain = classify_terrain(elevation)
    return (
        TerrainInfo(
            elevation=elevation,
            terrain=terrain,
            description=describe_terrain(elevation, terrain),
            confidence="high" if elevation is not None else "none",
        ),
        DataSource(
            field="elevation",
            provider=provider if elevation is not None else "unavailable",
            quality=quality,  # type: ignore[arg-type]
            note=None if elevation is not None else "No elevation provider answered.",
        ),
    )
