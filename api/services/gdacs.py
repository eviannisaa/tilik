"""Multi-hazard disaster events from GDACS.

GDACS (the EU's Global Disaster Alert and Coordination System) is the practical
answer to "what happened here besides earthquakes". It's free, needs no key, and
covers floods, volcanic eruptions, wildfires, tropical cyclones and droughts as
point features with dates.

Two things about it shape this module:

* **Its coordinates are regional.** A "Flood in Indonesia" point is a centroid
  for an affected area, not a street address. So these events get a much wider
  search radius than a seismic epicentre, and are tagged ``scope="regional"`` so
  the UI can say the location is approximate rather than implying precision.
* **One request returns only the most recent ~100 events nationwide.** That's
  enough to surface recent history live; `scripts/import_gdacs.py` walks
  year-by-year windows to load the full record into PostGIS.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from api.core.cache import TTLCache
from api.core.config import get_settings
from api.core.geo import haversine_meters
from api.core.http import fetch_json
from api.schemas.location import DisasterEvent

logger = logging.getLogger("tilik.services.gdacs")

PROVIDER = "GDACS"

#: GDACS event codes mapped to the type names this API exposes.
EVENT_TYPES: dict[str, str] = {
    "EQ": "earthquake",
    "TC": "cyclone",
    "FL": "flood",
    "VO": "volcanic eruption",
    "DR": "drought",
    "WF": "wildfire",
}

#: Earthquakes come from USGS with real epicentres, so exclude them here — it
#: also stops GDACS's quake stream crowding out everything else in the 100-record
#: response, which is the whole reason this module exists.
REQUESTED_TYPES = ("TC", "FL", "VO", "DR", "WF")

_cache = TTLCache(ttl_seconds=get_settings().cache_ttl_seconds)


def _parse_date(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).replace(tzinfo=UTC).isoformat()
    except ValueError:
        return None


def _title(properties: dict, event_type: str) -> str:
    """A readable title, preferring the name of the actual feature."""
    name = (properties.get("eventname") or "").strip()
    if name:
        # Volcano and cyclone events are named after the feature itself.
        return f"{event_type.title()}: {name}"
    return event_type.title()


def to_event(feature: dict, latitude: float, longitude: float) -> DisasterEvent | None:
    """Convert one GDACS feature into a normalised event."""
    properties = feature.get("properties") or {}
    coordinates = (feature.get("geometry") or {}).get("coordinates") or []
    if len(coordinates) < 2:
        return None

    code = properties.get("eventtype")
    event_type = EVENT_TYPES.get(code)
    if event_type is None:
        return None

    try:
        event_lng, event_lat = float(coordinates[0]), float(coordinates[1])
    except (TypeError, ValueError):
        return None

    url = properties.get("url")
    report_url = url.get("report") if isinstance(url, dict) else url

    return DisasterEvent(
        id=f"gdacs-{properties.get('eventid')}-{properties.get('episodeid')}",
        type=event_type,
        title=_title(properties, event_type),
        occurred_at=_parse_date(properties.get("fromdate")),
        magnitude=None,
        magnitude_unit=None,
        distance_meters=round(haversine_meters(latitude, longitude, event_lat, event_lng), 1),
        source=PROVIDER,
        url=report_url if isinstance(report_url, str) else None,
        scope="regional",
        severity=str(properties.get("alertlevel") or "").lower() or None,
    )


async def fetch_events(
    *,
    from_date: str,
    to_date: str,
    country: str | None = None,
) -> list[dict]:
    """Raw GDACS features for a date window. Shared with the ingest script."""
    settings = get_settings()
    params: dict[str, str] = {
        "fromDate": from_date,
        "toDate": to_date,
        "alertlevel": settings.gdacs_alert_levels,
        "eventlist": ";".join(REQUESTED_TYPES),
    }
    if country:
        params["country"] = country

    payload = await fetch_json(settings.gdacs_api_url, provider=PROVIDER, params=params)
    if not isinstance(payload, dict):
        return []
    return payload.get("features") or []


async def get_recent_events(latitude: float, longitude: float) -> list[DisasterEvent]:
    """Recent non-earthquake events near a point.

    Raises a :class:`~api.core.errors.TilikError` on failure so the caller can
    record the source as unavailable rather than silently reporting nothing.
    """
    settings = get_settings()
    cache_key = f"gdacs:{latitude:.2f}:{longitude:.2f}"

    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    since = (datetime.now(UTC) - timedelta(days=365 * settings.disaster_years)).date()
    features = await fetch_events(
        from_date=since.isoformat(),
        to_date=datetime.now(UTC).date().isoformat(),
        country=settings.gdacs_country or None,
    )

    events = [to_event(feature, latitude, longitude) for feature in features]
    nearby = [
        event
        for event in events
        if event is not None
        and (event.distance_meters or 0) <= settings.gdacs_radius_meters
    ]
    nearby.sort(key=lambda event: event.distance_meters or 0)

    _cache.set(cache_key, nearby)
    return nearby
