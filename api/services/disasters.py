"""Historical natural-disaster events around a point.

Each source answers a different question, and one event can be described by
more than one of them:

* **USGS** — the shock itself: magnitude, depth, intensity, a measured
  epicentre, and PAGER's estimated-impact alert. Earthquakes only.
* **PostGIS `disaster_events`** — recorded impact, from the imported BNPB DIBI
  archive: who died, who was displaced, what was destroyed, per district.
* An optional GeoJSON feed at `DISASTER_API_URL`.

:func:`_merge_matched_quakes` is the matcher: it decides when records from
different sources describe the same event and folds them into one
:class:`DisasterEvent`, so the shock is counted once while each district keeps
its own toll.

GDACS was a fourth and is deliberately gone. Two measurements settle it. Its
coordinates are centroids of affected regions, often a whole province, and it
publishes no casualty figures — an alert colour and a severity in hectares. And
as a pure enrichment it could never fire: its Indonesian record starts in 2023
while the DIBI archive ends in March 2020, so the two never overlap in time, and
for earthquakes the alert slot is already filled by USGS's own PAGER. It would
have been a source that matched nothing. `api/services/gdacs.py` and
`scripts/import_gdacs.py` remain for anyone who wants it back as a row source,
but nothing in a report calls them.

USGS results are filtered to events that plausibly reached people. A seismic
network reports what its instruments detected, which is a different question
from what a disaster history should answer: near Jakarta the catalogue is
dominated by magnitude 4–5 events 130–190 km down in the subducting slab, felt
by nobody. See :func:`_was_felt`.

An empty result is a normal answer, not an error.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from api.core.cache import TTLCache
from api.core.config import get_settings
from api.core.errors import TilikError
from api.core.geo import haversine_meters
from api.core.http import fetch_json
from api.db import repository
from api.schemas.common import DataSource
from api.schemas.location import DisasterEvent, DisasterHistory
from api.services import inarisk
from api.services import ncei_tsunami

logger = logging.getLogger("tilik.services.disasters")

USGS_PROVIDER = "usgs"
MAX_EVENTS = 12

#: How many events to ask USGS for before filtering. A seismic catalogue answers
#: with every event its network detected, most of which no one at this location
#: could have felt — so the unfelt ones are dropped here and a larger page is
#: fetched to keep MAX_EVENTS reachable afterwards.
USGS_FETCH_LIMIT = MAX_EVENTS * 6

#: How many stored rows to read before selecting. Reading exactly MAX_EVENTS
#: left `_select_events` nothing to choose from — its whole job is to spread the
#: list across hazard types, and it cannot do that if the query already cut the
#: candidates to the final count. One regency easily has 176 qualifying rows.
#:
#: Raised once the query started capping per area *and hazard*: more partitions
#: means more candidates, and the pool has to be wide enough that a nearby
#: district's rarer hazards still arrive — they are exactly the rows the matcher
#: needs to pair with a measured shock.
STORED_FETCH_LIMIT = MAX_EVENTS * 12

#: Most rows any one administrative area may take. Imported records share their
#: district's centroid, so without a cap the district whose centre happens to be
#: nearest wins every hazard bucket and fills the list on its own.
MAX_EVENTS_PER_AREA = 3

#: What each catalogue can actually return. USGS is a seismic network, so on its
#: own the "disaster history" section only ever covers earthquakes — floods,
#: landslides and eruptions need locally imported records.
USGS_TYPES = ("earthquake",)

#: Hazards the DesInventar/DIBI import adds, mirroring the vocabulary in
#: ``scripts/import_desinventar.py``. Used to say precisely what a report is
#: missing while nothing has been imported.
#:
#: Tsunami is the one that matters most and the one no live source has: USGS
#: publishes earthquakes only, and GDACS has no tsunami event type at all — it
#: answers 204 for ``eventlist=TS`` and only ever emits EQ, FL, TC, WF, DR, VO.
#: So on a beach in Banda Aceh, tsunami history is unavailable until the archive
#: is loaded, and the report has to say so rather than stay quiet.
#: Hazards read from a live catalogue rather than the imported archive.
#:
#: Both have a measured position: USGS publishes epicentres, NOAA/NCEI publishes
#: observed runups. The archive holds these hazards too, but only per district
#: and with no position inside it, so a row from each source would be the same
#: event listed twice — once locatable, once not.
EXTERNALLY_SOURCED_HAZARDS = frozenset({"earthquake", "tsunami"})

IMPORTABLE_TYPES = (
    "coastal erosion",
    "drought",
    "earthquake",
    "extreme weather",
    "fire",
    "flood",
    "landslide",
    "tsunami",
    "volcanic eruption",
    "wildfire",
)

#: Provider magnitude labels → the normalised scale stored on the event.
#: USGS publishes several moment-magnitude flavours (``mww`` from the W-phase,
#: ``mwc`` from a centroid solution) that differ in method, not in scale.
_MAGNITUDE_SCALES: dict[str, str] = {
    "mb": "mb",
    "mblg": "mb",
    "mbLg": "mb",
    "mw": "mw",
    "mww": "mw",
    "mwc": "mw",
    "mwb": "mw",
    "mwr": "mw",
    "mwp": "mw",
    "ms": "ms",
    "ms20": "ms",
    "mss": "ms",
    "ml": "ml",
    "mlg": "ml",
    "mlv": "ml",
    "md": "md",
    "mdl": "md",
    "m": "m",
}

#: Below this intensity nothing is felt, so an MMI figure this low is not
#: evidence that an event reached anybody. MMI II is "felt by a few at rest".
FELT_MMI_THRESHOLD = 2.0

_cache = TTLCache(ttl_seconds=get_settings().cache_ttl_seconds)


async def _archived_hazards() -> frozenset[str]:
    """`repository.archived_hazard_types`, read once per cache window.

    The set changes only when someone runs an importer, so paying for a round
    trip on every report would be waste.
    """
    cached = _cache.get("disasters:archived-hazards")
    if cached is not None:
        return cached
    hazards = await repository.archived_hazard_types()
    _cache.set("disasters:archived-hazards", hazards)
    return hazards


def _normalise_scale(raw: Any) -> tuple[str | None, str | None]:
    """Split a provider's magnitude label into ``(normalised, as-reported)``.

    An unrecognised label becomes ``"other"`` rather than being dropped: the
    magnitude is still real, and the original string is preserved alongside it.
    """
    if raw is None:
        return None, None
    text = str(raw).strip()
    if not text:
        return None, None
    return _MAGNITUDE_SCALES.get(text.lower(), "other"), text


def _was_felt(event: DisasterEvent, max_depth_km: float) -> bool:
    """Whether this quake plausibly reached people, rather than only seismographs.

    Three rules, in order of how much they know:

    1. An intensity reading decides on its own, either way. It is USGS's own
       aggregate judgement of what the shaking was, so ``mmi`` of 1 — "not
       felt" — rules an event out even when a couple of reports exist, and an
       intensity at or above :data:`FELT_MMI_THRESHOLD` rules one in whatever
       its depth.
    2. Failing that, any felt report at all counts as evidence.
    3. Failing both, depth decides. USGS computes intensity for anything
       significant, so silence plus great depth is the signature of an event
       nobody noticed.

    This is the difference between a useful disaster history and a seismograph
    log. Within 50 km of Serpong the catalogue holds 16 events of magnitude 4.5
    and up; 13 of them sit between 95 and 175 km down in the subducting slab
    with no intensity and no reports, including the "0 km NE of Serpong,
    4.5 mb" of March 2018 — an epicentre named after the town, 139 km beneath
    it, that nobody in the town experienced.
    """
    if event.intensity_mmi is not None:
        return event.intensity_mmi >= FELT_MMI_THRESHOLD
    if event.felt_reports:
        return True
    if event.depth_km is None:
        return True
    return event.depth_km <= max_depth_km


def _parse_usgs_feature(
    feature: dict[str, Any], latitude: float, longitude: float
) -> DisasterEvent | None:
    properties = feature.get("properties") or {}
    coordinates = (feature.get("geometry") or {}).get("coordinates") or []
    if len(coordinates) < 2:
        return None

    event_lng, event_lat = float(coordinates[0]), float(coordinates[1])
    has_depth = len(coordinates) > 2 and coordinates[2] is not None
    depth_km = float(coordinates[2]) if has_depth else None
    epoch_ms = properties.get("time")
    occurred_at = (
        datetime.fromtimestamp(epoch_ms / 1000, tz=UTC).isoformat()
        if isinstance(epoch_ms, (int, float))
        else None
    )

    magnitude = properties.get("mag")
    scale, scale_source = _normalise_scale(properties.get("magType"))

    # ShakeMap's modelled intensity is the better figure where it exists: it is
    # computed for every significant event, whereas `cdi` depends on somebody
    # filing a report — and outside the US almost nobody does.
    modelled, reported = properties.get("mmi"), properties.get("cdi")
    if modelled is not None:
        intensity, basis = float(modelled), "modelled"
    elif reported is not None:
        intensity, basis = float(reported), "reported"
    else:
        intensity, basis = None, None

    felt = properties.get("felt")

    return DisasterEvent(
        id=str(feature.get("id") or properties.get("code") or f"usgs-{epoch_ms}"),
        type="earthquake",
        title=str(properties.get("place") or "Earthquake"),
        occurred_at=occurred_at,
        magnitude=float(magnitude) if magnitude is not None else None,
        magnitude_scale=scale,
        magnitude_scale_source=scale_source,
        depth_km=round(depth_km, 1) if depth_km is not None else None,
        intensity_mmi=round(intensity, 1) if intensity is not None else None,
        intensity_basis=basis,
        felt_reports=int(felt) if isinstance(felt, (int, float)) else None,
        distance_meters=round(haversine_meters(latitude, longitude, event_lat, event_lng), 1),
        distance_basis="measured",
        source="USGS",
        url=properties.get("url"),
        # PAGER's estimated-impact level, where USGS ran one.
        severity=str(properties.get("alert") or "").lower() or None,
    )


async def _fetch_earthquakes(
    latitude: float, longitude: float, radius_meters: int, years: int
) -> list[DisasterEvent]:
    """Shocks within `radius_meters`, which earthquakes may be given their own.

    Callers pass `settings.earthquake_radius_meters` when it is set and the
    shared radius otherwise. See the note on that setting for why an epicentre
    72 km away can matter more than one 5 km away — and for what widening it
    costs.
    """
    settings = get_settings()
    start = (datetime.now(UTC) - timedelta(days=365 * years)).date().isoformat()

    payload = await fetch_json(
        settings.earthquake_api_url,
        provider=USGS_PROVIDER,
        params={
            "format": "geojson",
            "latitude": latitude,
            "longitude": longitude,
            "maxradiuskm": radius_meters / 1000,
            "starttime": start,
            "minmagnitude": settings.disaster_min_magnitude,
            "orderby": "magnitude",
            "limit": USGS_FETCH_LIMIT,
        },
        headers={"Accept": "application/geo+json"},
    )

    features = (payload or {}).get("features", []) if isinstance(payload, dict) else []
    events = [_parse_usgs_feature(feature, latitude, longitude) for feature in features]
    return [
        event
        for event in events
        if event is not None and _was_felt(event, settings.disaster_max_depth_km)
    ]


def _parse_geojson_feature(
    feature: dict[str, Any], latitude: float, longitude: float
) -> DisasterEvent | None:
    """Read a generic GeoJSON point feature from `DISASTER_API_URL`.

    Property names follow the common `type`/`title`/`date` convention; anything
    missing is simply left blank rather than dropping the event.
    """
    properties = feature.get("properties") or {}
    coordinates = (feature.get("geometry") or {}).get("coordinates") or []
    if len(coordinates) < 2:
        return None

    try:
        event_lng, event_lat = float(coordinates[0]), float(coordinates[1])
    except (TypeError, ValueError):
        return None

    scale, scale_source = _normalise_scale(
        properties.get("magnitudeScale") or properties.get("magnitudeUnit")
    )

    return DisasterEvent(
        id=str(feature.get("id") or properties.get("id") or f"{event_lat},{event_lng}"),
        type=str(properties.get("type") or properties.get("jenis") or "disaster"),
        title=str(properties.get("title") or properties.get("kejadian") or "Recorded event"),
        occurred_at=properties.get("date") or properties.get("tanggal"),
        magnitude=properties.get("magnitude"),
        magnitude_scale=scale,
        magnitude_scale_source=scale_source,
        distance_meters=round(haversine_meters(latitude, longitude, event_lat, event_lng), 1),
        source=str(properties.get("source") or "custom-feed"),
        url=properties.get("url"),
    )


async def _fetch_shocks(
    latitude: float, longitude: float, moments: list[datetime]
) -> list[DisasterEvent]:
    """Candidate causes for recorded earthquake loss, over a wide radius.

    Deliberately separate from the display query. What gets listed is bounded by
    the reader's radius; what *caused* a district's damage is not, and matching
    inside the display radius attributed Palu's 3,624 deaths to an M5.8
    aftershock because the M7.5 mainshock was 72 km out.
    """
    if not moments:
        return []

    settings = get_settings()
    window = timedelta(hours=SAME_QUAKE_HOURS)
    payload = await fetch_json(
        settings.earthquake_api_url,
        provider=USGS_PROVIDER,
        params={
            "format": "geojson",
            "latitude": latitude,
            "longitude": longitude,
            "maxradiuskm": SHOCK_SEARCH_KM,
            "starttime": (min(moments) - window).date().isoformat(),
            "endtime": (max(moments) + window).date().isoformat(),
            "minmagnitude": SHOCK_MIN_MAGNITUDE,
            "orderby": "magnitude",
            "limit": 500,
        },
        headers={"Accept": "application/geo+json"},
    )
    features = (payload or {}).get("features", []) if isinstance(payload, dict) else []
    parsed = [_parse_usgs_feature(f, latitude, longitude) for f in features]
    return [event for event in parsed if event is not None]


async def _fetch_custom_feed(
    latitude: float, longitude: float, radius_meters: int
) -> list[DisasterEvent]:
    settings = get_settings()
    if not settings.disaster_api_url:
        return []

    payload = await fetch_json(
        settings.disaster_api_url,
        provider="disaster-feed",
        params={"lat": latitude, "lng": longitude, "radius": radius_meters},
    )

    features = (payload or {}).get("features", []) if isinstance(payload, dict) else []
    events = [_parse_geojson_feature(feature, latitude, longitude) for feature in features]
    return [
        event
        for event in events
        if event is not None
        and (event.distance_meters is None or event.distance_meters <= radius_meters)
    ]


def _significance(event: DisasterEvent) -> tuple[float, float]:
    """How much an event matters here, as ``(severity, -distance)``.

    Distance alone is a poor measure of which events belong in a short list.
    The NTT earthquake of August 2026 proves it: the M7.7 sat 4.9 km from a pin
    while three M5.0 aftershocks sat 2.1, 2.2 and 4.3 km away, so a
    nearest-three rule showed the aftershocks and dropped the earthquake that
    actually mattered. A magnitude 7.7 five kilometres off dominates a
    magnitude 5 two kilometres off by any reading a person would recognise.

    Severity is whatever the record can say: its magnitude, else the shaking it
    produced, else the harm it did. Distance breaks ties, so among equals the
    nearer one still wins.

    Magnitude leads, and that ordering was the other way round until earthquakes
    were given their own 200 km reach. `intensity_mmi` from USGS is the event's
    *highest* intensity anywhere, not the intensity here — a distinction that
    barely mattered inside 25 km and matters a great deal outside it. Ranking on
    it put an M5.8 at 103 km, whose MMI 8.9 was recorded near Poso, above the
    M7.5 at 72 km that levelled Palu. Magnitude describes the event itself and
    does not silently belong to somewhere else.
    """
    if event.magnitude is not None:
        severity = event.magnitude
    elif event.intensity_mmi is not None:
        severity = event.intensity_mmi
    elif event.impact is not None:
        harm = max(
            event.impact.deaths or 0,
            event.impact.missing or 0,
            (event.impact.displaced or 0) // 100,
        )
        # Kept on the same rough scale as a magnitude so one bucket can mix
        # loss records and measured shocks without either drowning the other.
        severity = min(10.0, harm ** 0.5)
    else:
        severity = 0.0
    return (severity, -(_by_distance(event)))


def _by_distance(event: DisasterEvent) -> float:
    """Sort key that treats zero as nearest, not as missing.

    ``event.distance_meters or inf`` reads as "unknown goes last", but 0.0 is
    falsy, so an event *at* the pin sorted last instead of first. Only reachable
    since area boundaries replaced centroids: a pin inside a district is 0 m
    from it, and the district the reader is standing in was pushed to the bottom
    of its own report.
    """
    return float("inf") if event.distance_meters is None else event.distance_meters


def _display_order(event: DisasterEvent) -> tuple[int, float]:
    """Sort key grouping rows by how well their distance is known.

    The figure column says three different kinds of thing, and reading down a
    list that interleaves them means re-reading what each number means on every
    row. Grouping them puts the measured distances together, then the rows whose
    area contains the coordinate, then the rows that can only state a lower
    bound:

        24 km from coordinate     ← measured, exact
        Same district             ← inside the area; no distance exists
        ≥ 5.9 km away             ← a bound, not a measurement
        ~ 63 km to area centre    ← bounds nothing in either direction

    Inside a group the nearest comes first. Severity still decides *which*
    events reach the list — `_significance` ranks the buckets and fills the
    remaining slots — so the M7.7 that three closer M5.0 aftershocks once
    crowded out is still selected; it just sits below them when they are nearer.
    Ranking and reading order are separate questions, and this answers only the
    second.
    """
    if event.distance_basis == "measured":
        rank = 0
    elif event.distance_basis == "area_edge":
        # Zero means the coordinate is inside, and then no distance exists at
        # all; anything else is the nearest the event could have been.
        rank = 1 if not event.distance_meters else 2
    else:
        rank = 3

    return (rank, _by_distance(event))


def _select_events(
    events: list[DisasterEvent], limit: int, per_type: int
) -> list[DisasterEvent]:
    """Pick a spread of hazard types rather than N of whichever is commonest.

    Seismic networks log far more events than any other catalogue, so a plain
    nearest-first cut fills the whole list with earthquakes — in Jakarta that
    hid every flood, which is the one hazard that actually matters there. This
    takes each type's nearest event first, then fills any remaining slots by
    distance.

    One district also can't take the whole list. Imported records share their
    district's centroid, so whichever district's centre happens to be nearest
    wins every type bucket at once: around Serpong, Kota Jakarta Selatan sits
    16 km away with a record of five hazard types and took 8 of 12 slots, while
    the district the pin is actually inside — Kota Tangerang Selatan, 18 km to
    its centre — showed nothing at all. Two kilometres of centroid arithmetic
    decided that a land check in Serpong displayed Jakarta's history. Capping
    each area lets the neighbours in without needing to know which district
    holds the pin.
    """
    ordered = sorted(events, key=_by_distance)

    # Buckets rank by significance, not by distance: a nearest-three rule inside
    # a hazard drops the event a reader came for whenever smaller ones happen to
    # sit marginally closer.
    buckets: dict[str, list[DisasterEvent]] = {}
    for event in ordered:
        buckets.setdefault(event.type, []).append(event)
    for kind in buckets:
        buckets[kind].sort(key=_significance, reverse=True)

    selected: list[DisasterEvent] = []
    per_area: dict[str, int] = {}

    def take(event: DisasterEvent) -> bool:
        """Accept an event unless its area already has its share.

        Measured epicentres have no ``area_name`` and are never capped: each one
        is its own location, so they cannot crowd a district out.
        """
        area = event.area_name
        if area is not None:
            if per_area.get(area, 0) >= MAX_EVENTS_PER_AREA:
                return False
            per_area[area] = per_area.get(area, 0) + 1
        selected.append(event)
        return True

    # Round-robin by rank: every type's nearest before any type's second.
    for rank in range(per_type):
        for kind in sorted(buckets):
            if rank < len(buckets[kind]) and len(selected) < limit:
                take(buckets[kind][rank])

    if len(selected) < limit:
        # Filling by distance flooded the list with whatever happened to be
        # nearest: a pin on the NTT epicentre drew eight near-identical M5.0
        # aftershocks and left no room for anything else. Significance fills the
        # remaining slots for the same reason it ranks the buckets.
        chosen = {event.id for event in selected}
        for event in sorted(ordered, key=_significance, reverse=True):
            if len(selected) >= limit:
                break
            if event.id not in chosen:
                take(event)

    selected.sort(key=_display_order)
    return selected


#: How far the shock that caused a district's damage may be from the pin.
#:
#: Not the display radius. Palu 2018 settles it: the M7.5 that killed 3,624
#: people in Kota Palu had its epicentre 72 km north, well outside a 25 km
#: search, so matching within the display radius found only the M5.8 aftershock
#: 16 km away and credited it with every death. A damaging earthquake is
#: routinely felt and destructive far from its epicentre, so the search for the
#: cause has to be much wider than the search for what to list.
SHOCK_SEARCH_KM = 400

#: Below this, a shock is not a plausible cause of recorded district-wide loss,
#: and including small ones invites an aftershock to outrank the real culprit
#: when the mainshock is missing from the catalogue window.
SHOCK_MIN_MAGNITUDE = 5.0

#: How far apart two records of one earthquake may be dated before they stop
#: counting as the same event.
#:
#: DIBI dates events in local time, USGS in UTC, so the same shock can land on
#: different calendar days: Yogyakarta 2006 is `2006-05-26 22:53 UTC` and
#: `2006-05-27` to DIBI. Indonesia spans UTC+7 to UTC+9, so a day boundary plus
#: the widest offset needs more than 24 hours of slack.
SAME_QUAKE_HOURS = 36


def _records_harm(event: DisasterEvent) -> bool:
    """Whether a row carries any figure above zero.

    A loss record with nothing recorded adds an area name and nothing else, so
    it is neither worth merging nor worth fetching.
    """
    impact = event.impact
    if impact is None:
        return False
    return any(
        (value or 0) > 0
        for value in (
            impact.deaths,
            impact.missing,
            impact.injured,
            impact.displaced,
            impact.houses_destroyed,
            impact.houses_damaged,
        )
    )


def _merge_matched_tsunamis(events: list[DisasterEvent]) -> list[DisasterEvent]:
    """Fold a measured runup into the loss record of the same wave.

    One tsunami arrives twice. NOAA/NCEI publishes where the water was observed
    and how high it reached; DIBI publishes what it cost, once per district.
    Palu 2018 turns up as `Kota Palu` with 3,624 dead and as `Palu City (a13)`
    at 10.73 m, and Aceh 2004 as `Kota Banda Aceh`, `Kota Sabang` and a 50.9 m
    observation — the same wave listed three times.

    The height is attached to the *nearest* matching loss record only. Aceh's
    50.9 m was measured near Banda Aceh; copying it onto Kota Sabang 24 km away
    would invent a local figure NCEI never recorded there. So one district gains
    the height it was measured in, the observation stops being its own row, and
    no other district is given a number that is not its own.
    """
    observed = [
        e
        for e in events
        if e.source.startswith(ncei_tsunami.NCEI_PROVIDER) and e.occurred_at
    ]
    losses = [
        e
        for e in events
        if "tsunami" in e.hazard_types
        and e.scope != "point"
        and e.occurred_at
        and _records_harm(e)
    ]
    if not observed or not losses:
        return events

    window = timedelta(hours=SAME_QUAKE_HOURS)
    absorbed: set[str] = set()

    for runup in observed:
        when = datetime.fromisoformat(runup.occurred_at)
        near = [
            loss
            for loss in losses
            if abs(datetime.fromisoformat(loss.occurred_at) - when) <= window
        ]
        if not near:
            continue
        host = min(near, key=_by_distance)
        absorbed.add(runup.id)
        # Only ever fills a gap. A district that already carries a measured
        # height keeps it.
        if host.water_height_m is None:
            host.water_height_m = runup.water_height_m

    return [e for e in events if e.id not in absorbed]


def _merge_matched_quakes(
    events: list[DisasterEvent], shocks: list[DisasterEvent] | None = None
) -> list[DisasterEvent]:
    """Fold a measured epicentre into the loss records of the same earthquake.

    One earthquake reaches the list from two directions. USGS publishes the
    shock — magnitude, depth, intensity, a real epicentre. DIBI publishes what
    it did, once per affected district. Yogyakarta 2006 arrives as four rows:
    `10 km E of Pundong M6.3` from USGS, and Bantul (4,143 dead), Kota
    Yogyakarta (218) and Sleman (243) from DIBI.

    The three DIBI rows are not duplicates of each other — each is a different
    district's toll, and collapsing them would throw away 461 deaths. The USGS
    row *is* a duplicate of all three, so it is removed and its seismic
    readings are copied onto them. The result is one row per district that
    carries both the shaking and the cost, and the shock counted once.

    Only the largest shock in the window is treated as the same event. That day
    also brought M4.8 and M4.6 aftershocks, which are genuinely separate
    earthquakes and stay as their own rows.
    """
    losses = [
        e
        for e in events
        if "earthquake" in e.hazard_types and e.scope != "point" and e.occurred_at
    ]
    listed = [
        e
        for e in events
        if "earthquake" in e.hazard_types and e.scope == "point" and e.occurred_at
    ]
    # Candidate causes come from the wide search; the listed shocks are also
    # candidates so that one already on screen is absorbed rather than doubled.
    measured = list({e.id: e for e in [*listed, *(shocks or [])]}.values())
    if not losses or not measured:
        return events

    window = timedelta(hours=SAME_QUAKE_HOURS)
    absorbed: set[str] = set()

    for loss in losses:
        # Absorb only when the loss record actually adds something. A row that
        # records no casualties and no displacement contributes an area name and
        # nothing else, while the measured row it would replace carries a real
        # epicentre — and, being area-bound, the merged row then competes under
        # the per-area cap and can lose its slot, which made the event vanish
        # from the list altogether. Trivial records are left unpaired.
        if not _records_harm(loss):
            continue
        when = datetime.fromisoformat(loss.occurred_at)
        near = [
            m
            for m in measured
            if abs(datetime.fromisoformat(m.occurred_at) - when) <= window
        ]
        if not near:
            continue
        # The main shock is the one the recorded damage belongs to.
        shock = max(near, key=lambda m: m.magnitude or 0)
        absorbed.add(shock.id)

        # Only fill gaps: a loss record has no seismic readings of its own, and
        # nothing it does hold should be overwritten.
        if loss.magnitude is None:
            loss.magnitude = shock.magnitude
            loss.magnitude_scale = shock.magnitude_scale
            loss.magnitude_scale_source = shock.magnitude_scale_source
        if loss.depth_km is None:
            loss.depth_km = shock.depth_km
        if loss.intensity_mmi is None:
            loss.intensity_mmi = shock.intensity_mmi
            loss.intensity_basis = shock.intensity_basis
        if loss.felt_reports is None:
            loss.felt_reports = shock.felt_reports
        if loss.url is None:
            loss.url = shock.url

    # Only rows that were on screen can be removed from it. A cause found by
    # the wide search was never listed, so absorbing it changes nothing but the
    # readings it lends.
    return [e for e in events if e.id not in absorbed]


def _deduplicate(events: list[DisasterEvent]) -> list[DisasterEvent]:
    seen: set[str] = set()
    unique: list[DisasterEvent] = []
    for event in events:
        if event.id in seen:
            continue
        seen.add(event.id)
        unique.append(event)
    return unique


async def get_disaster_history(
    latitude: float,
    longitude: float,
    *,
    local_events: list[DisasterEvent] | None = None,
    skip_database: bool = False,
) -> tuple[DisasterHistory, list[DataSource]]:
    """Merge every configured disaster source for this point.

    `local_events` carries rows a caller already read from PostGIS;
    `skip_database` says that read happened and returned nothing.
    """
    settings = get_settings()
    radius = settings.disaster_radius_meters
    years = settings.disaster_years
    # Both default to the shared figures, so one radius and one window cover
    # every hazard unless someone deliberately widens one.
    quake_radius = settings.earthquake_radius_meters or radius
    tsunami_window = settings.tsunami_years or years

    sources: list[DataSource] = []
    events: list[DisasterEvent] = []

    # Every figure in the section should mean the same thing. With this on, a
    # row is kept only when its coordinate is the event's own measured location,
    # so a distance is a distance rather than the offset to an area's middle.
    measured_only = settings.disaster_require_measured_location

    stored = local_events or []
    if not stored and not skip_database:
        stored = await repository.disasters_near(
            latitude,
            longitude,
            radius,
            years,
            limit=STORED_FETCH_LIMIT,
            per_area=MAX_EVENTS_PER_AREA,
        )
    if measured_only:
        stored = [event for event in stored if event.scope == "point"]
    # Earthquakes come from USGS and tsunamis from NOAA/NCEI. Both publish a
    # measured position — an epicentre, an observed runup — so both give a real
    # distance from the checked coordinate, which a district-wide archive row
    # never can.
    #
    # The cost is stated plainly because it is large and deliberate: DIBI is the
    # only source here that counts casualties, so excluding it from these two
    # hazards removes every recorded earthquake and tsunami death from the
    # section — 170,791 of them, Palu's 3,624 and Aceh's 128,728 included. USGS
    # publishes PAGER *estimates* and NCEI counts casualties per event rather
    # than per observation, so neither replaces them. Every other hazard —
    # flood, landslide, drought, extreme weather, fire, wildfire, eruption,
    # coastal erosion — still comes from the archive with its tolls intact.
    # Keyed on position, not on provenance. What disqualifies an archive row for
    # these two hazards is that it has no measured location — the archive stores
    # 0.0 for every coordinate — so the rule is written as that, and a row that
    # does carry one survives whatever supplied it. Keying on hazard alone would
    # have dropped a measured epicentre that happened to reach this list through
    # the database.
    stored = [
        event
        for event in stored
        if event.scope == "point"
        or not set(event.hazard_types) & EXTERNALLY_SOURCED_HAZARDS
    ]
    if stored:
        events.extend(stored)
        sources.append(DataSource(field="disasters", provider="postgis", quality="database"))

    if not settings.enable_external_apis:
        sources.append(
            DataSource(
                field="disasters",
                provider="unavailable",
                quality="unavailable",
                note="External APIs are disabled.",
            )
        )
    else:
        cache_key = f"disasters:{latitude:.3f}:{longitude:.3f}:{measured_only}"
        cached = _cache.get(cache_key)
        if cached is not None:
            events.extend(cached)
            sources.append(DataSource(field="disasters", provider="USGS", quality="live"))
            sources.append(
                DataSource(field="disasters", provider=ncei_tsunami.NCEI_PROVIDER, quality="live")
            )
        else:
            remote: list[DisasterEvent] = []

            # Concurrently: three independent providers, and awaiting them in
            # turn added their latencies together for no reason. USGS answers in
            # ~2.5s and NOAA/NCEI pages through up to three requests at ~6.5s,
            # so serially they cost 9s of the 20s the frontend allows the whole
            # report.
            quakes, runups, feed = await asyncio.gather(
                _fetch_earthquakes(latitude, longitude, quake_radius, years),
                ncei_tsunami.fetch_runups(latitude, longitude, radius, tsunami_window),
                _fetch_custom_feed(latitude, longitude, radius),
                return_exceptions=True,
            )

            try:
                if isinstance(quakes, BaseException):
                    raise quakes
                remote.extend(quakes)
                sources.append(DataSource(field="disasters", provider="USGS", quality="live"))
            except TilikError as exc:
                logger.warning("Earthquake lookup degraded: %s", exc)
                sources.append(
                    DataSource(
                        field="disasters",
                        provider="USGS",
                        quality="unavailable",
                        note="The earthquake catalogue did not answer.",
                    )
                )

            try:
                if isinstance(runups, BaseException):
                    raise runups
                remote.extend(runups)
                sources.append(
                    DataSource(field="disasters", provider=ncei_tsunami.NCEI_PROVIDER, quality="live")
                )
            except TilikError as exc:
                logger.warning("Tsunami lookup degraded: %s", exc)
                sources.append(
                    DataSource(
                        field="disasters",
                        provider=ncei_tsunami.NCEI_PROVIDER,
                        quality="unavailable",
                        note="The tsunami database did not answer.",
                    )
                )

            try:
                if isinstance(feed, BaseException):
                    raise feed
                remote.extend(feed)
            except TilikError as exc:
                logger.warning("Custom disaster feed degraded: %s", exc)

            if measured_only:
                remote = [event for event in remote if event.scope == "point"]

            _cache.set(cache_key, remote)
            events.extend(remote)

    # No archive lookup for earthquake losses.
    #
    # `repository.quake_losses_near` exists to fetch DIBI's per-district death
    # tolls for each shock on screen, and calling it here would put back exactly
    # the rows `EXTERNALLY_SOURCED_HAZARDS` excludes — the filter above runs on
    # the display pool, and this ran after it. Earthquakes are USGS's alone now,
    # so the pairing has nothing left to pair with. The query itself is kept for
    # anyone who wants the tolls back.
    causes: list[DisasterEvent] = []

    # The cause of recorded loss need not be near the pin, so it is searched for
    # separately and widely.
    harmed = [
        datetime.fromisoformat(event.occurred_at)
        for event in events
        if event.occurred_at
        and event.scope != "point"
        and "earthquake" in event.hazard_types
        and _records_harm(event)
    ]
    if harmed and settings.enable_external_apis:
        try:
            causes = await _fetch_shocks(latitude, longitude, harmed)
        except TilikError as exc:
            logger.warning("Shock lookup degraded: %s", exc)

    # Merge before selecting: an absorbed USGS row must not occupy a slot, and
    # the loss records need their seismic readings in place before the list is
    # ordered and capped.
    events = _select_events(
        _merge_matched_tsunamis(_merge_matched_quakes(_deduplicate(events), causes)),
        MAX_EVENTS,
        settings.disaster_events_per_type,
    )

    has_live_source = any(source.quality in {"live", "database"} for source in sources)

    # Name what was searched, so an empty section can't be mistaken for an
    # all-clear on hazards no catalogue here ever covered.
    searched: list[str] = []
    covered: list[str] = []

    # What the archive covers nationally, not what it happened to return here —
    # see `repository.archived_hazard_types`. Under `measured_only` it covers
    # nothing: every archive row is discarded for having no coordinate, so the
    # search did run but none of its answers survive to be reported on.
    archived = frozenset() if measured_only else await _archived_hazards()
    # The archive is no longer read for earthquake or tsunami, so it must not be
    # credited for them — otherwise two catalogues appear to answer a hazard
    # only one is consulted for.
    archived = archived - EXTERNALLY_SOURCED_HAZARDS
    if archived or stored:
        searched.append("locally imported records (PostGIS)")
    # The union of what the catalogue holds and what we have in hand. Rows alone
    # understate it (a pin with no eruption nearby was still checked against
    # every eruption on record); the catalogue alone drops to nothing when the
    # database is unreachable but a caller passed rows anyway. Hazards, not
    # display labels — an "earthquake and tsunami" record registers under both.
    covered.extend(archived)
    covered.extend(hazard for event in stored for hazard in event.hazard_types)
    if any(source.provider == "USGS" and source.quality == "live" for source in sources):
        searched.append("USGS earthquake catalogue")
        covered.extend(USGS_TYPES)
    if any(
        source.provider == ncei_tsunami.NCEI_PROVIDER and source.quality == "live"
        for source in sources
    ):
        searched.append("NOAA NCEI tsunami database")
        covered.append("tsunami")
    if settings.disaster_api_url:
        searched.append("configured disaster feed")

    covered = sorted(set(covered))
    missing_hazards = sorted(set(IMPORTABLE_TYPES) - set(covered))

    note = None
    if measured_only:
        note = (
            "Showing only events with a measured location, so every distance "
            "here is a real distance from the coordinate you entered. That "
            "leaves earthquakes alone: BNPB's DIBI records, every flood, "
            "landslide, windstorm, drought and wildfire, carry no coordinate "
            "and are held per district, so they are excluded. Unset "
            "DISASTER_REQUIRE_MEASURED_LOCATION to include them."
        )
    elif not has_live_source:
        note = "We couldn't reach any disaster data source for this check."
    elif set(covered) <= set(USGS_TYPES):
        # Nothing but the seismic catalogue answered. Say so rather than let an
        # earthquake-only list read as the full picture.
        note = (
            "Only earthquakes were searched here. A seismic catalogue records "
            "tremors, not damage, so nothing in this list speaks to flood, "
            "landslide or eruption history, and the absence of those is not an "
            "all-clear."
        )
    elif missing_hazards and inarisk.in_coverage(latitude, longitude):
        # Name what is actually absent rather than a fixed example list. The
        # hardcoded version said "floods, landslides and windstorms" on a beach
        # in Banda Aceh and never mentioned tsunami — the one hazard a reader
        # standing there most needs to know is unsearched. No live source has
        # tsunami at all: USGS is earthquakes only, and GDACS answers 204 for
        # its tsunami code.
        note = (
            f"No source we check covers {', '.join(missing_hazards)} here, so "
            "this list says nothing either way about those. Everything else "
            "was searched."
        )
    elif not events:
        note = (
            f"No events at or above magnitude {settings.disaster_min_magnitude} were "
            f"recorded within {radius // 1000} km in the last {years} years."
        )

    return (
        DisasterHistory(
            radius_meters=radius,
            events=events,
            # Announced only when it actually differs. Unset means earthquakes
            # were searched over the same radius as everything else, and there is
            # then nothing for a caption to explain.
            earthquake_radius_meters=(
                quake_radius
                if quake_radius != radius
                and any(
                    source.provider == "USGS" and source.quality == "live"
                    for source in sources
                )
                else None
            ),
            searched_years=years,
            tsunami_years=(
                tsunami_window
                if tsunami_window != years
                and any(
                    source.provider == ncei_tsunami.NCEI_PROVIDER and source.quality == "live"
                    for source in sources
                )
                else None
            ),
            confidence="high" if has_live_source else "none",
            searched_sources=searched,
            covered_types=covered,
            note=note,
        ),
        sources,
    )
