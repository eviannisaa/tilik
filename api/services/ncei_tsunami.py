"""Observed tsunami arrivals, from NOAA/NCEI's historical tsunami database.

NCEI publishes two tables, and only one of them answers the question this
section asks.

`tsunamis/events` is one row per tsunami with its *source* coordinate — where
the wave started — plus the total casualties for the whole event. `Palu 2018`
is a single row at 0.256°S, 119.846°E with 4,340 deaths. Using that coordinate
would repeat the mistake GDACS was removed for: the source of the 2004 Indian
Ocean tsunami sits 250 km off Aceh, so a plot in Banda Aceh would read as 250 km
from a tsunami that destroyed it, and a plot 20 km inland would read as closer to
it than the coast.

`tsunamis/runups` is one row per *observation* — a place the wave was recorded
reaching, with a measured coordinate and, in 197 of 200 rows sampled, the height
it reached there. Palu 2018 has 195 of them. That is what "was this place hit,
and how high did the water get" means, so runups are what this module reads.

Casualties are deliberately left off. NCEI records them per event, not per
runup: attaching 4,340 deaths to an observation 20 km from a pin would state a
local toll the database never claimed. Wave height is per-observation and is
reported.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from math import cos, radians

from api.core.config import get_settings
from api.core.geo import haversine_meters
from api.core.http import fetch_json
from api.schemas.location import DisasterEvent

logger = logging.getLogger(__name__)

NCEI_PROVIDER = "NOAA NCEI"
SOURCE_LABEL = "NOAA NCEI (tsunami runups)"

#: The API rejects anything above this, and pages beyond it.
PAGE_SIZE = 200
#: A mega-event fills a page with its own observations — Palu alone has 195
#: within one 60 km box — so a single page can hide every older tsunami behind
#: one recent one. Three pages covers that without letting a coastal pin walk
#: the whole Pacific record.
MAX_PAGES = 3


def _occurred_at(row: dict) -> str | None:
    """A UTC timestamp, from NCEI's separate date and time columns.

    Only the year is guaranteed. Month and day are missing on older records and
    the time is missing on about one row in two hundred, so each falls back
    rather than discarding the observation: a tsunami known only by its year is
    still a tsunami that reached this coast.
    """
    year = row.get("year")
    if not isinstance(year, int):
        return None
    try:
        return datetime(
            year,
            row.get("month") or 1,
            row.get("day") or 1,
            row.get("hour") or 0,
            row.get("minute") or 0,
            int(row.get("second") or 0),
            tzinfo=UTC,
        ).isoformat()
    except ValueError:
        # Feb 30 and friends: NCEI holds a few impossible dates.
        return datetime(year, 1, 1, tzinfo=UTC).isoformat()


def _title(row: dict) -> str:
    """The place the wave was observed, cased like the rest of the section."""
    name = str(row.get("locationName") or row.get("area") or "").strip()
    if not name:
        return "Tsunami"
    return " ".join(part.capitalize() for part in name.split())


async def fetch_runups(
    latitude: float, longitude: float, radius_meters: int, years: int
) -> list[DisasterEvent]:
    """Tsunami observations within `radius_meters` of a point.

    One row per tsunami, positioned at its *nearest* observation to the pin —
    the closest the water is recorded as having come. Farther observations of
    the same wave are dropped rather than listed, so a mega-event contributes
    one row instead of 195.
    """
    settings = get_settings()
    earliest = datetime.now(UTC).year - years

    # A bounding box wide enough to contain the circle, which is then filtered
    # by true distance below. Longitude degrees shrink with latitude.
    span_lat = radius_meters / 111_320
    span_lng = radius_meters / max(111_320 * cos(radians(latitude)), 1.0)

    box = {
        "minLatitude": round(latitude - span_lat, 4),
        "maxLatitude": round(latitude + span_lat, 4),
        "minLongitude": round(longitude - span_lng, 4),
        "maxLongitude": round(longitude + span_lng, 4),
        "minYear": earliest,
        "itemsPerPage": PAGE_SIZE,
    }

    async def page_of(page: int) -> list[dict]:
        payload = await fetch_json(
            settings.ncei_tsunami_api_url,
            provider=NCEI_PROVIDER,
            params={**box, "page": page},
            headers={"Accept": "application/json"},
        )
        items = (payload or {}).get("items", []) if isinstance(payload, dict) else []
        return [item for item in items if isinstance(item, dict)]

    # Every page at once, not one after another.
    #
    # Requested in sequence this was the slowest thing in the whole report: three
    # round trips at about four seconds each, 12.6s for a pin in Palu, where the
    # 2018 tsunami alone has 196 observations inside 25 km. Nothing on page one
    # decides whether pages two and three are wanted, so there is no reason to
    # wait for it — and a page that does not exist answers with an empty list,
    # which costs a request and no correctness.
    pages = await asyncio.gather(
        *(page_of(page) for page in range(1, MAX_PAGES + 1)),
        return_exceptions=True,
    )

    rows: list[dict] = []
    for index, page in enumerate(pages, start=1):
        if isinstance(page, BaseException):
            # One bad page is not a reason to report no tsunami at all.
            logger.warning("NCEI page %d failed: %s", index, page)
            continue
        rows.extend(page)

    if all(isinstance(page, list) and len(page) == PAGE_SIZE for page in pages):
        logger.info(
            "NCEI runups truncated at %d pages for %.3f,%.3f", MAX_PAGES, latitude, longitude
        )

    # One entry per tsunami, built from two different observations on purpose.
    #
    # The distance is the nearest one: the closest the water is recorded as
    # having come to this pin. The height is the *highest* within the radius,
    # not the nearest one's — and that distinction is the whole reason this is
    # not a one-liner. Runups mix measurement types: tide gauges, satellite
    # altimetry and post-tsunami surveys all land in the same table. Within
    # 25 km of Banda Aceh the 2004 tsunami has observations from 2.1 m to
    # 50.9 m, and the closest to the city centre is a 0.6 m gauge reading. A row
    # saying the 2004 tsunami reached 0.6 m here would be the most misleading
    # figure in this section.
    #
    # `doubtful` marks records NCEI itself questions; `publish` false marks ones
    # it withholds.
    grouped: dict[object, dict] = {}
    for row in rows:
        lat, lng = row.get("latitude"), row.get("longitude")
        if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
            continue
        if str(row.get("doubtful") or "").lower() == "y" or row.get("publish") is False:
            continue
        distance = haversine_meters(latitude, longitude, float(lat), float(lng))
        if distance > radius_meters:
            continue

        # The year window has to be enforced here. `minYear` is accepted by the
        # runups endpoint and then ignored: asking for 2001 onwards near Banda
        # Aceh returns rows from 1861. Left to the API, a 25-year search
        # returned an 1885 tsunami.
        year = row.get("year")
        if not isinstance(year, int) or year < earliest:
            continue

        key = row.get("tsunamiEventId") or row.get("id")
        height = row.get("runupHt")
        height = float(height) if isinstance(height, (int, float)) else None
        entry = grouped.get(key)
        if entry is None:
            grouped[key] = {"distance": distance, "nearest": row, "height": height}
            continue
        if distance < entry["distance"]:
            entry["distance"] = distance
            entry["nearest"] = row
        if height is not None and (entry["height"] is None or height > entry["height"]):
            entry["height"] = height

    events: list[DisasterEvent] = []
    for entry in grouped.values():
        row = entry["nearest"]
        distance = entry["distance"]
        height = entry["height"]
        occurred_at = _occurred_at(row)
        if occurred_at is None:
            continue
        event_id = row.get("tsunamiEventId")
        events.append(
            DisasterEvent(
                id=f"ncei-{row.get('id')}",
                type="tsunami",
                hazard_types=["tsunami"],
                title=_title(row),
                source=SOURCE_LABEL,
                url=(
                    f"https://www.ngdc.noaa.gov/hazel/view/hazards/tsunami/event-more-info/{event_id}"
                    if event_id
                    else None
                ),
                occurred_at=occurred_at,
                # An observation is a place, measured — unlike the source
                # coordinate this module deliberately does not use.
                scope="point",
                distance_meters=round(distance, 1),
                distance_basis="measured",
                water_height_m=height,
            )
        )

    return events
