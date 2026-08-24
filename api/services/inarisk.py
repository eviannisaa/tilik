"""BNPB InaRISK hazard indices.

InaRISK publishes national hazard models as ArcGIS ImageServers where each pixel
holds a 0..1 hazard index. Querying a single point is an `identify` call:

    {INARISK_BASE_URL}/{layer}/ImageServer/identify
        ?geometry={"x":<lng>,"y":<lat>,"spatialReference":{"wkid":4326}}
        &geometryType=esriGeometryPoint&f=json

A pixel outside the modelled area answers ``"NoData"``, which means "not in a
mapped hazard zone" — not "no hazard". BNPB's server is noticeably slower and
less reliable than the other providers, so every call here is retried once and
failures degrade the section rather than the request.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
from typing import Literal
from urllib.parse import urlencode

from api.core.cache import TTLCache
from api.core.config import get_settings
from api.core.errors import TilikError, UpstreamUnavailableError
from api.core.geo import haversine_meters
from api.core.http import fetch_json
from api.db import repository
from api.db.repository import HazardCellReading
from api.schemas.common import ConfidenceLevel, RiskLevel
from api.schemas.location import HazardIndex, HazardReading

logger = logging.getLogger("tilik.services.inarisk")

PROVIDER = "inarisk"

#: Whether a layer answered, answered with no coverage, or failed outright.
HazardStatus = Literal["ok", "no_data", "unavailable", "out_of_coverage"]

#: InaRISK layer names, keyed by the hazard we expose in the API. Names come
#: from BNPB's own service listing at {INARISK_BASE_URL}?f=json.
HAZARD_LAYERS: dict[str, str] = {
    "flood": "layer_bahaya_banjir",
    "flashFlood": "layer_bahaya_banjir_bandang",
    "landslide": "layer_bahaya_tanah_longsor",
    "earthquake": "layer_bahaya_gempabumi",
    "liquefaction": "layer_bahaya_likuefaksi",
    # BNPB publishes the same rasters under two service names. `layer_bahaya_*`
    # is normally the fast one (~0.15 s), but its tsunami service hangs: every
    # read operation — getSamples, identify, exportImage — never returns, while
    # the service metadata answers instantly, so the data is there and only that
    # endpoint is broken. `INDEKS_BAHAYA_TSUNAMI` serves the same raster and
    # works. Verified equal on four hazards where both respond: gempabumi,
    # banjir, likuefaksi and tanahlongsor return byte-identical values at four
    # test points. It is slower (7–30 s against 0.15 s), which is survivable for
    # `import_inarisk.py` and marginal against `inarisk_timeout_seconds` — one
    # more reason to ingest rather than read this layer live.
    # Re-test `layer_bahaya_tsunami` occasionally; if it recovers, switch back.
    "tsunami": "INDEKS_BAHAYA_TSUNAMI",
    "coastalErosion": "layer_bahaya_gelombang_ekstrim_dan_abrasi",
    "volcanic": "layer_bahaya_letusan_gunungapi",
    "extremeWeather": "layer_bahaya_cuaca_ekstrim",
    "drought": "layer_bahaya_kekeringan",
    "wildfire": "layer_bahaya_kebakaran_hutan_dan_lahan",
}

#: Human labels, matching BNPB's own wording.
HAZARD_LABELS: dict[str, str] = {
    "flood": "Flood",
    "flashFlood": "Flash flood",
    "landslide": "Landslide",
    "earthquake": "Earthquake",
    "liquefaction": "Liquefaction",
    "tsunami": "Tsunami",
    "coastalErosion": "Waves & erosion",
    "volcanic": "Volcanic eruption",
    "extremeWeather": "Extreme weather",
    "drought": "Drought",
    "wildfire": "Forest & land fire",
}

#: Native resolution of the InaRISK rasters, in metres.
NATIVE_RESOLUTION_M = 100
#: Rough metres per degree of latitude; fine for laying out a sample grid.
METERS_PER_DEGREE = 111_320.0

#: InaRISK's modelled extent, derived from the ImageServer's own metadata
#: (EPSG:3395 bounds converted to degrees). Roughly Indonesia's bounding box.
#:
#: Checked before any request: outside it, every layer would answer NoData, and
#: rendering that as "no hazard mapped" would imply a clean result for somewhere
#: the model never looked. It also saves eleven pointless round trips.
COVERAGE_BOUNDS = {"west": 95.0, "east": 141.1, "south": -11.1, "north": 6.0}


def in_coverage(latitude: float, longitude: float) -> bool:
    """Whether InaRISK models hazards anywhere near this point."""
    return (
        COVERAGE_BOUNDS["south"] <= latitude <= COVERAGE_BOUNDS["north"]
        and COVERAGE_BOUNDS["west"] <= longitude <= COVERAGE_BOUNDS["east"]
    )


#: How far to look for each hazard, in metres.
#:
#: One radius for everything doesn't work. Flood, liquefaction and seismic
#: hazard are broad surfaces, so the plot's own pixel is the answer. Tsunami and
#: coastal erosion are thin bands at the shoreline; landslide follows hillslopes;
#: volcanic hazard rings a mountain. Those are *offset* from a plot rather than
#: absent, and searching only 500 m reported them as "no hazard" for a town
#: 1–3 km from the coast — which is how this was found.
HAZARD_RADIUS_M: dict[str, int] = {
    "flood": 1_000,
    "flashFlood": 1_000,
    "liquefaction": 1_000,
    "earthquake": 1_000,
    "extremeWeather": 1_000,
    "drought": 1_000,
    "wildfire": 2_500,
    "landslide": 2_500,
    "tsunami": 5_000,
    "coastalErosion": 5_000,
    "volcanic": 10_000,
}

#: Radius within which a hazard counts as affecting the plot itself rather than
#: merely being in the neighbourhood. Deliberately below every search radius, so
#: a hazard found at the edge of a search is reported as context and does not
#: drive the concern level.
AT_PLOT_METERS = 500

#: Sampled at native resolution out to this distance, then more coarsely, so a
#: single request stays under the provider's 1000-point cap.
DENSE_RADIUS_M = 500
COARSE_STEP_M = 250
RAY_COUNT = 16

#: BNPB classifies the index in equal thirds: rendah / sedang / tinggi.
LOW_MAX = 1 / 3
MEDIUM_MAX = 2 / 3

_cache = TTLCache(ttl_seconds=get_settings().cache_ttl_seconds)


def classify_index(index: float | None) -> RiskLevel:
    """Map a 0..1 InaRISK index onto BNPB's three hazard classes."""
    if index is None:
        return "unknown"
    if index <= LOW_MAX:
        return "low"
    if index <= MEDIUM_MAX:
        return "medium"
    return "high"


def describe_reading(
    level: RiskLevel,
    index: float | None,
    status: HazardStatus,
    *,
    from_postgis: bool = False,
    within_meters: float | None = None,
) -> str:
    """BNPB-flavoured wording for one hazard reading."""
    if status == "out_of_coverage":
        return "Outside InaRISK's modelled area. BNPB maps Indonesia only."
    if status == "unavailable":
        return "BNPB's hazard service didn't answer for this layer."
    if status == "no_data" or index is None:
        return (
            "InaRISK models no hazard of this kind at or near this point. "
            "That is not a guarantee of safety."
        )

    # BNPB publishes these classes in Indonesian; keep both so the number and
    # the official wording are traceable back to the source.
    indonesian = {"low": "rendah", "medium": "sedang", "high": "tinggi"}[level]
    sentence = f"{level.title()} ({indonesian}). Index {index:.2f} of 1.00"

    # Several layers (tsunami, coastal erosion) are thin bands along the shore,
    # so "nearby" is the honest and more useful reading.
    if within_meters is not None and within_meters >= 1:
        sentence += f", found {round(within_meters)} m away"
    else:
        sentence += ", at this point"

    sentence += "."
    if from_postgis:
        sentence += " Read from ingested InaRISK data."
    return sentence


def reading_from_cell(key: str, cell: HazardCellReading) -> HazardReading:
    """Build a reading from an ingested `hazard_cells` row."""
    level = classify_index(cell.hazard_index)
    return HazardReading(
        key=key,
        label=HAZARD_LABELS[key],
        index=cell.hazard_index,
        level=level,
        status="ok",
        source="postgis",
        resolution_meters=cell.resolution_meters,
        within_meters=cell.distance_meters,
        description=describe_reading(
            level,
            cell.hazard_index,
            "ok",
            from_postgis=True,
            within_meters=cell.distance_meters,
        ),
    )


def _neighbourhood_points(
    latitude: float, longitude: float, radius_meters: int
) -> list[tuple[float, float, float]]:
    """Sample points around a coordinate, centre first.

    Returns ``(lat, lng, metres_from_centre)``. Dense at native 100 m resolution
    close in, where the exact value matters, then radial spokes further out to
    detect a hazard band the plot sits near. Long-range spokes can slip between
    two very narrow features, so distances beyond `DENSE_RADIUS_M` are treated as
    indicative — which is what `withinMeters` communicates.
    """
    if radius_meters <= 0:
        return [(latitude, longitude, 0.0)]

    shrink = max(0.05, math.cos(math.radians(latitude)))
    step_lat = NATIVE_RESOLUTION_M / METERS_PER_DEGREE
    step_lng = NATIVE_RESOLUTION_M / (METERS_PER_DEGREE * shrink)

    points = [(latitude, longitude, 0.0)]

    # Dense inner grid.
    rings = int(min(radius_meters, DENSE_RADIUS_M) // NATIVE_RESOLUTION_M)
    for row in range(-rings, rings + 1):
        for col in range(-rings, rings + 1):
            if row == 0 and col == 0:
                continue
            sample_lat = latitude + row * step_lat
            sample_lng = longitude + col * step_lng
            distance = haversine_meters(latitude, longitude, sample_lat, sample_lng)
            if distance <= DENSE_RADIUS_M:
                points.append((sample_lat, sample_lng, distance))

    # Radial spokes beyond the dense core.
    for ray in range(RAY_COUNT):
        bearing = 2 * math.pi * ray / RAY_COUNT
        for distance in range(
            DENSE_RADIUS_M + COARSE_STEP_M, radius_meters + 1, COARSE_STEP_M
        ):
            sample_lat = latitude + (distance * math.cos(bearing)) / METERS_PER_DEGREE
            sample_lng = longitude + (distance * math.sin(bearing)) / (
                METERS_PER_DEGREE * shrink
            )
            points.append((sample_lat, sample_lng, float(distance)))

    return points


async def _sample_layer(
    key: str, layer: str, latitude: float, longitude: float
) -> tuple[float | None, float | None]:
    """Highest hazard value near a point, and how far away it was found.

    Returns ``(index, metres_from_point)``. ``(None, None)`` means the layer
    answered but models nothing in range.
    """
    settings = get_settings()
    radius = HAZARD_RADIUS_M.get(key, settings.inarisk_neighbourhood_meters)
    points = _neighbourhood_points(latitude, longitude, radius)

    payload = await fetch_json(
        f"{settings.inarisk_base_url.rstrip('/')}/{layer}/ImageServer/getSamples",
        provider=PROVIDER,
        method="POST",
        data=urlencode(
            {
                "geometry": json.dumps(
                    {
                        "points": [[lng, lat] for lat, lng, _ in points],
                        "spatialReference": {"wkid": 4326},
                    },
                    separators=(",", ":"),
                ),
                "geometryType": "esriGeometryMultipoint",
                "returnFirstValueOnly": "true",
                "f": "json",
            }
        ),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=settings.inarisk_timeout_seconds,
    )

    if not isinstance(payload, dict):
        return None, None

    # ArcGIS reports its own errors inside a 200 response.
    if "error" in payload:
        logger.warning("InaRISK %s error: %s", layer, payload["error"])
        raise UpstreamUnavailableError(detail=f"InaRISK rejected the {layer} request")

    at_point: float | None = None
    nearby_index: float | None = None
    nearby_distance: float | None = None

    for sample in payload.get("samples", []):
        raw = sample.get("value")
        if raw in (None, "", "NoData"):
            continue
        try:
            value = float(raw)
            position = int(sample["locationId"])
        except (KeyError, TypeError, ValueError):
            continue
        if position >= len(points):
            continue

        # locationId 0 is always the queried coordinate itself.
        if position == 0:
            at_point = value
            continue

        distance = points[position][2]
        # Among neighbours keep the strongest, breaking ties by proximity.
        closer_tie = (
            nearby_index is not None
            and value == nearby_index
            and nearby_distance is not None
            and distance < nearby_distance
        )
        if nearby_index is None or value > nearby_index or closer_tie:
            nearby_index, nearby_distance = value, distance

    # The point's own pixel is the authoritative reading where it exists. The
    # neighbourhood is a safety net for hazards modelled as thin bands, not a
    # way to inflate a value the model already gave for this exact spot.
    if at_point is not None:
        return at_point, 0.0

    return nearby_index, nearby_distance


async def get_hazard(key: str, latitude: float, longitude: float) -> HazardReading:
    """Read one hazard layer live. Never raises.

    There is no retry here on purpose: BNPB's failure mode is a slow timeout, so
    a second attempt would double the report's worst case for very little gain.
    Outcomes are cached either way, so reloading a page doesn't re-hammer a
    service that is already struggling.
    """
    layer = HAZARD_LAYERS[key]
    cache_key = f"inarisk:{key}:{latitude:.4f}:{longitude:.4f}"

    cached: tuple[float | None, float | None, HazardStatus] | None = _cache.get(cache_key)
    if cached is not None:
        index, distance, status = cached
    else:
        try:
            index, distance = await _sample_layer(key, layer, latitude, longitude)
            status = "ok" if index is not None else "no_data"
        except TilikError as exc:
            logger.warning("InaRISK %s unavailable: %s", layer, exc)
            index, distance, status = None, None, "unavailable"
        _cache.set(cache_key, (index, distance, status))

    level = classify_index(index) if status == "ok" else "unknown"
    return HazardReading(
        key=key,
        label=HAZARD_LABELS[key],
        index=index,
        level=level,
        status=status,
        source="inarisk" if status == "ok" else "none",
        within_meters=distance,
        description=describe_reading(level, index, status, within_meters=distance),
    )


def _no_data_reading(key: str) -> HazardReading:
    """An authoritative "nothing modelled here", from ingested coverage."""
    return HazardReading(
        key=key,
        label=HAZARD_LABELS[key],
        index=None,
        level="unknown",
        status="no_data",
        source="postgis",
        description=describe_reading("unknown", None, "no_data"),
    )


async def get_hazards(
    latitude: float,
    longitude: float,
    keys: tuple[str, ...] | None = None,
    *,
    local: dict[str, HazardCellReading] | None = None,
    covered: frozenset[str] | None = None,
) -> dict[str, HazardReading]:
    """Hazard readings for a point, preferring ingested data over the live API.

    PostGIS is asked first: `scripts/import_inarisk.py` samples BNPB's rasters
    into `hazard_cells`, and a local `ST_Intersects` is both faster and far more
    reliable than BNPB's server. Only hazards with no ingested coverage fall
    through to the live ImageServers.

    Pass `local` when the caller has already run the composite PostGIS analysis,
    to avoid querying the database twice for the same point.
    """
    settings = get_settings()
    selected = keys or tuple(HAZARD_LAYERS)

    if not in_coverage(latitude, longitude):
        return {
            key: HazardReading(
                key=key,
                label=HAZARD_LABELS[key],
                index=None,
                level="unknown",
                status="out_of_coverage",
                description=describe_reading("unknown", None, "out_of_coverage"),
            )
            for key in selected
        }

    if local is None:
        local = await repository.hazard_near(
            latitude, longitude, settings.inarisk_neighbourhood_meters
        )
    if covered is None:
        covered = await repository.hazard_coverage_at(latitude, longitude)

    readings: dict[str, HazardReading] = {
        key: reading_from_cell(key, local[key]) for key in selected if key in local
    }

    # A hazard whose area we ingested but that has no cell here is answered, not
    # missing. Treating it as missing would send us to BNPB for every point in
    # every area we already sampled — exactly the slow path ingesting removes.
    for key in selected:
        if key not in readings and key in covered:
            readings[key] = _no_data_reading(key)

    missing = tuple(key for key in selected if key not in readings)
    if not missing:
        return readings

    if not settings.enable_external_apis:
        return readings

    selected = missing

    # Hard ceiling on the whole group. BNPB occasionally stops answering
    # altogether, and a location report must not hang waiting for it.
    budget = settings.inarisk_timeout_seconds + 4.0

    try:
        live = await asyncio.wait_for(
            asyncio.gather(
                *(get_hazard(key, latitude, longitude) for key in selected),
                return_exceptions=True,
            ),
            timeout=budget,
        )
    except TimeoutError:
        logger.warning("InaRISK exceeded its %.0fs budget; skipping hazards", budget)
        return readings

    for key, fetched in zip(selected, live, strict=True):
        if isinstance(fetched, HazardReading):
            readings[key] = fetched
        else:
            logger.warning("InaRISK %s failed: %s", key, fetched)
    return readings


def build_hazard_index(readings: dict[str, HazardReading]) -> HazardIndex:
    """Wrap raw readings into the API's hazard section.

    Confidence reflects coverage, not certainty. The three cases below read very
    differently to someone deciding whether to buy, so they are kept apart:
    layers that answered, layers with no modelled hazard, and layers we simply
    could not reach.
    """
    if not readings:
        return HazardIndex(
            readings=[],
            confidence="none",
            note=(
                "BNPB's InaRISK service didn't answer for this point, so there is "
                "no official hazard index to show."
            ),
        )

    ordered = [readings[key] for key in HAZARD_LAYERS if key in readings]
    answered = [r for r in ordered if r.status == "ok"]
    unreachable = [r for r in ordered if r.status == "unavailable"]

    if ordered and all(r.status == "out_of_coverage" for r in ordered):
        return HazardIndex(
            readings=ordered,
            confidence="none",
            note=(
                "This point is outside InaRISK's modelled area. BNPB covers "
                "Indonesia only. No hazard index applies here, which is not the "
                "same as no hazard."
            ),
        )

    confidence: ConfidenceLevel
    note: str | None = None

    if answered:
        confidence = "high" if len(answered) == len(ordered) else "medium"
        if unreachable:
            names = ", ".join(r.label.lower() for r in unreachable)
            note = f"InaRISK didn't answer for: {names}."
    elif unreachable:
        # Nothing came back. Say so plainly rather than implying safety.
        confidence = "none"
        note = (
            "BNPB's InaRISK service is unreachable right now, so none of these "
            "hazard layers could be checked."
        )
    else:
        confidence = "low"
        note = (
            "InaRISK answered but has no modelled hazard covering this point. "
            "That is not the same as 'no hazard'."
        )

    return HazardIndex(readings=ordered, confidence=confidence, note=note)
