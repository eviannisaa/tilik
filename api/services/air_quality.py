"""Air quality at the nearest monitoring station, from WAQI.

Every other section of this report is a model, a catalogue or press coverage.
InaRISK says what *could* happen, USGS and NOAA/NCEI say what was *recorded*,
Google News says what was *reported*. None of them is an instrument. This one
is: the number it returns was measured by a machine standing in the open air.

The coverage that machine represents is thinner than the project's 11,000+
stations suggests. Indonesia has 25 of them, all BMKG's, roughly one per region:
Jakarta, Semarang, Yogyakarta, Palembang, Medan, Makassar, Bekasi and Tangerang
Selatan fall within 25 km of one, while Surabaya is 79 km from the nearest,
Balikpapan 90 km, Bandung 120 km and Denpasar 297 km. So for a good deal of the
country this section reports a coverage gap rather than a reading, and that is
the accurate answer rather than a shortcoming of the lookup.

Source choice: **WAQI's geolocalized feed** (`/feed/geo:{lat};{lng}/`). It takes
a coordinate directly, needs a free token, answers in well under a second, and
its quota is 1,000 requests per second, which is generous past anything a report
does. OpenAQ was the obvious alternative: it publishes raw concentrations and no
AQI, which would mean implementing the EPA breakpoint tables here and owning the
arithmetic for six pollutants. WAQI publishes the converted index, so the scale
lives with the people who maintain it.

Three things shape this module.

* **It answers with a station, not with your point.** WAQI picks the nearest
  monitor and never says how far away it is. That distance is computed here from
  `data.city.geo` and it drives the confidence level, because a reading from
  40 km away is an estimate for a plot of land rather than a measurement of it.
* **Its errors arrive with HTTP 200.** A bad token is
  `{"status": "error", "data": "Invalid key"}` and no nearby monitor is
  `{"status": "nug", "data": "Unknown station"}`. Both decode as valid JSON, so
  `fetch_json` cannot tell them from success, and read as success a
  misconfigured deployment would report clean air everywhere. Same failure mode
  as Overpass's `remark`, handled the same way: check the envelope first.
* **`iaqi` values are already AQI**, not concentrations. WAQI converts each
  pollutant onto the index before publishing, so nothing here converts anything,
  and each pollutant bands with the same thresholds as the headline figure. That
  block also carries weather (`t`, `h`, `p`, `w`), which is not pollution and is
  not listed.
"""

from __future__ import annotations

import logging
from typing import Any

from api.core.cache import TTLCache
from api.core.config import get_settings
from api.core.errors import TilikError
from api.core.geo import haversine_meters
from api.core.http import fetch_json
from api.schemas.common import ConfidenceLevel, DataSource, RiskLevel
from api.schemas.location import (
    AirQuality,
    AirQualityAttribution,
    AqiBand,
    PollutantReading,
)

logger = logging.getLogger("tilik.services.air_quality")

PROVIDER = "waqi"

#: US EPA band boundaries, as `(upper bound, key, published name)`.
#:
#: The only place these numbers live. They are the published scale, not a Tilik
#: invention, which is why the band names are the EPA's own wording rather than
#: something friendlier: a reader who wants to check them can.
BANDS: tuple[tuple[int, AqiBand, str], ...] = (
    (50, "good", "Good"),
    (100, "moderate", "Moderate"),
    (150, "unhealthySensitive", "Unhealthy for sensitive groups"),
    (200, "unhealthy", "Unhealthy"),
    (300, "veryUnhealthy", "Very unhealthy"),
)

#: Anything above the last boundary above.
HAZARDOUS: tuple[AqiBand, str] = ("hazardous", "Hazardous")

#: The six bands mapped onto the report's three-tone palette.
#:
#: `moderate` stays `low`, which is deliberate. The palette has three tones and
#: clay means hazard everywhere else in this report, so colouring AQI 60 as clay
#: would put it alongside a high tsunami index. Nothing is lost by it: the EPA
#: band name is displayed as published, so a reader sees "Moderate" either way.
BAND_LEVELS: dict[AqiBand, RiskLevel] = {
    "good": "low",
    "moderate": "low",
    "unhealthySensitive": "medium",
    "unhealthy": "high",
    "veryUnhealthy": "high",
    "hazardous": "high",
    "unknown": "unknown",
}

#: The `iaqi` keys that are pollution, and what to call them.
#:
#: `iaqi` also carries `t`, `h`, `p` and `w`: temperature, humidity, pressure
#: and wind. Those are weather. Listing them in a pollutant table would put
#: "25.5" under a column headed AQI and invite the reader to band it.
POLLUTANT_LABELS: dict[str, str] = {
    "pm25": "PM2.5",
    "pm10": "PM10",
    "o3": "Ozone (O3)",
    "no2": "NO2",
    "so2": "SO2",
    "co": "CO",
}

#: Reading order for the table: the two that drive Indonesian AQI first.
POLLUTANT_ORDER: tuple[str, ...] = ("pm25", "pm10", "o3", "no2", "so2", "co")

#: Inside this radius a station reading is fairly called a measurement here.
#:
#: Five kilometres is roughly the scale over which urban PM2.5 stays comparable
#: on a given day. Beyond it the reading is still worth showing, and stops being
#: a measurement of this address.
AT_POINT_METERS = 5_000

#: Where "the wider region" stops being a fair description of the distance.
#:
#: Nothing is suppressed at any distance; this only decides which sentence is
#: true. Between roughly 25 and 100 km the station is somewhere in the same
#: region, and a reading is weak local context. Past that it is a different part
#: of the country: Bandung's nearest monitor is Kemayoran in Jakarta at 120 km,
#: and the `demo` token answers Shanghai for every coordinate on earth, 4,440 km
#: from Jakarta. Calling either one "this region" would be the section's only
#: false statement.
ANOTHER_REGION_METERS = 100_000

_cache = TTLCache(ttl_seconds=get_settings().cache_ttl_seconds)


def classify_aqi(aqi: float | None) -> tuple[AqiBand, str, RiskLevel]:
    """Band one AQI value, returning its key, its published name and its tone."""
    if aqi is None:
        return "unknown", "Unknown", "unknown"

    for upper, key, label in BANDS:
        if aqi <= upper:
            return key, label, BAND_LEVELS[key]

    key, label = HAZARDOUS
    return key, label, BAND_LEVELS[key]


def confidence_for(distance_meters: float | None) -> ConfidenceLevel:
    """How much this reading says about the checked point, from how far it came.

    The badge vocabulary is shared with every other section: `high` renders as
    "Measured", `medium` as "Modelled", `low` as "Estimated". A monitor down the
    road measured this air. One in the next kabupaten did not, and calling its
    figure a measurement of this plot would be the one dishonest number on the
    page.
    """
    if distance_meters is None:
        return "none"
    if distance_meters <= AT_POINT_METERS:
        return "high"
    if distance_meters <= get_settings().waqi_max_station_meters:
        return "medium"
    return "low"


def _value_of(entry: Any) -> float | None:
    """The `v` of an `iaqi` entry, when it is a number."""
    if not isinstance(entry, dict):
        return None
    value = entry.get("v")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _pollutants(iaqi: Any, dominant: str | None) -> list[PollutantReading]:
    """The pollution rows of an `iaqi` block, in reading order."""
    if not isinstance(iaqi, dict):
        return []

    readings: list[PollutantReading] = []
    for key in POLLUTANT_ORDER:
        value = _value_of(iaqi.get(key))
        if value is None:
            continue
        band, band_label, level = classify_aqi(value)
        readings.append(
            PollutantReading(
                key=key,
                label=POLLUTANT_LABELS[key],
                aqi=value,
                band=band,
                band_label=band_label,
                level=level,
                dominant=key == dominant,
            )
        )
    return readings


def _attributions(raw: Any) -> list[AirQualityAttribution]:
    """Who to credit. Required by WAQI's terms, so a missing list is a bug."""
    if not isinstance(raw, list):
        return []

    credits: list[AirQualityAttribution] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        url = str(entry.get("url") or "").strip() or None
        credits.append(AirQualityAttribution(name=name, url=url))
    return credits


def _station_distance(city: Any, latitude: float, longitude: float) -> float | None:
    """How far `data.city.geo` sits from the checked point."""
    if not isinstance(city, dict):
        return None
    geo = city.get("geo")
    if not isinstance(geo, list) or len(geo) != 2:
        return None
    try:
        station_lat, station_lng = float(geo[0]), float(geo[1])
    except (TypeError, ValueError):
        return None
    return round(haversine_meters(latitude, longitude, station_lat, station_lng), 1)


def describe_reading(air: AirQuality) -> str:
    """One or two sentences a reader can act on.

    States the band, names what set it, and says where the figure came from,
    because the distance is what decides how much of this is about their plot.
    No em dashes: each clause is its own sentence.
    """
    if air.aqi is None or air.band == "unknown" or not air.band_label:
        return "No air-quality reading is available for this point."

    opening = f"AQI {air.aqi}, which the US EPA scale calls {air.band_label.lower()}."

    # "X is the pollutant setting it" claims X beat the others. Where a station
    # measures one pollutant there were no others, and the headline figure is
    # just that pollutant's own number. Same reasoning as the table's "sets the
    # index" marker, which is dropped in the same case.
    driver = ""
    if air.dominant_label and len(air.pollutants) > 1:
        driver = f" {air.dominant_label} is the pollutant setting it."
    elif len(air.pollutants) == 1:
        driver = f" {air.pollutants[0].label} is the only pollutant this station measures."

    place = ""
    if air.station_distance_meters is not None:
        kilometres = air.station_distance_meters / 1000
        if air.station_distance_meters <= AT_POINT_METERS:
            place = (
                f" Measured {kilometres:.1f} km away, which is close enough to describe "
                "this point."
            )
        elif air.station_distance_meters <= get_settings().waqi_max_station_meters:
            place = (
                f" Measured {kilometres:.1f} km away, so read it as the air over this "
                "area rather than this address."
            )
        elif air.station_distance_meters <= ANOTHER_REGION_METERS:
            place = (
                f" Measured {kilometres:.0f} km away, which is far enough that it describes "
                "the region rather than this address."
            )
        else:
            # The band that has to survive 120 km and 4,440 km alike. Anything
            # phrased as "this area" or "the region" is simply untrue here.
            place = (
                f" The nearest station is {kilometres:.0f} km away, in another part of the "
                "country, so this is background rather than a reading of the air here."
            )

    return f"{opening}{driver}{place} This is one hour's reading, not a pattern."


def parse_feed(payload: Any, latitude: float, longitude: float) -> AirQuality:
    """Turn a WAQI response into a section, including its failure cases.

    Kept apart from the fetch so every branch is testable without a network
    call, the same split as `news.parse_feed`. Every unhappy path returns an
    `AirQuality` rather than raising: the caller has already decided that a
    missing air-quality section must not cost the reader the rest of the report.
    """
    if not isinstance(payload, dict):
        return AirQuality(
            status="unavailable",
            description="The air-quality service sent something we could not read.",
            note="WAQI answered in an unexpected shape.",
        )

    status = str(payload.get("status") or "").lower()
    data = payload.get("data")

    if status != "ok":
        # WAQI reports both of these with HTTP 200, so this is the only place
        # they can be told apart. `nug` is its code for "no usable geo", which
        # is a fact about the map; "invalid key" is a fact about our .env.
        detail = data if isinstance(data, str) else ""
        if "key" in detail.lower():
            logger.warning("WAQI rejected the token: %s", detail)
            return AirQuality(
                status="unavailable",
                description="The air-quality service rejected our credentials.",
                note=(
                    "WAQI would not accept the configured token, so no reading could be "
                    "taken. This is a setup problem on our side, not a gap in the data."
                ),
            )
        return AirQuality(
            status="no_station",
            description="No monitoring station reports air quality near this point.",
            note=(
                "Air quality is measured at fixed stations, and WAQI has none within "
                "reach of this coordinate. That is a gap in coverage, not clean air."
            ),
        )

    if not isinstance(data, dict):
        return AirQuality(
            status="unavailable",
            description="The air-quality service sent something we could not read.",
            note="WAQI answered ok with no reading attached.",
        )

    aqi_raw = data.get("aqi")
    aqi: int | None = None
    if isinstance(aqi_raw, (int, float)) and not isinstance(aqi_raw, bool):
        aqi = int(aqi_raw)
    elif isinstance(aqi_raw, str) and aqi_raw.strip().isdigit():
        # WAQI sends "-" for a station that is online but not reporting.
        aqi = int(aqi_raw.strip())

    if aqi is None:
        return AirQuality(
            status="no_station",
            description="The nearest monitoring station is not reporting a reading.",
            note=(
                "WAQI knows of a station here but has no current index from it. "
                "Stations go offline for maintenance and calibration."
            ),
        )

    band, band_label, level = classify_aqi(aqi)
    dominant = str(data.get("dominentpol") or "").strip() or None
    city = data.get("city")
    time = data.get("time")

    reading = AirQuality(
        aqi=aqi,
        band=band,
        level=level,
        band_label=band_label,
        dominant_pollutant=dominant,
        dominant_label=POLLUTANT_LABELS.get(dominant or ""),
        pollutants=_pollutants(data.get("iaqi"), dominant),
        pollutants_possible=len(POLLUTANT_LABELS),
        station_name=(
            str(city.get("name") or "").strip() or None if isinstance(city, dict) else None
        ),
        station_url=(
            str(city.get("url") or "").strip() or None if isinstance(city, dict) else None
        ),
        station_distance_meters=_station_distance(city, latitude, longitude),
        measured_at=(
            str(time.get("iso") or "").strip() or None if isinstance(time, dict) else None
        ),
        attributions=_attributions(data.get("attributions")),
        status="ok",
        description="",
    )
    reading.confidence = confidence_for(reading.station_distance_meters)
    reading.description = describe_reading(reading)
    return reading


def _degraded(reading: AirQuality) -> tuple[AirQuality, DataSource]:
    """Pair a non-`ok` reading with the provenance the report footer shows.

    `no_station` is not a failure and must not be reported as one. WAQI answered,
    and the answer was that it has no monitor within reach. Filed as
    `unavailable` it would put "the air-quality service" in the report's gaps
    notice, telling the reader a provider was down when nothing was down. This
    is the same distinction `news` draws between `no_results` and `unavailable`.
    """
    answered = reading.status == "no_station"
    return (
        reading,
        DataSource(
            field="airQuality",
            provider=PROVIDER,
            quality="live" if answered else "unavailable",
            note=reading.note,
        ),
    )


def _unavailable(
    note: str, *, status: str = "unavailable", description: str | None = None
) -> tuple[AirQuality, DataSource]:
    return _degraded(
        AirQuality(
            status=status,  # type: ignore[arg-type]
            description=description or note,
            note=note,
        )
    )


async def get_air_quality(latitude: float, longitude: float) -> tuple[AirQuality, DataSource]:
    """The air-quality reading nearest one point.

    Never raises. Air quality is not what someone came to Tilik for, so any
    failure costs this section and explains itself, rather than costing the
    reader the terrain, the flood risk and the disaster history too.
    """
    settings = get_settings()

    if not settings.enable_air_quality:
        return _unavailable(
            "Air quality is turned off for this deployment.",
            status="disabled",
        )

    if not settings.enable_external_apis:
        return _unavailable("External APIs are disabled, so air quality wasn't looked up.")

    if not settings.waqi_api_token:
        return _unavailable(
            "No WAQI token is configured, so air quality could not be looked up. "
            "A free one takes a minute to request.",
            status="not_configured",
        )

    # Three decimals, roughly 100 m. Four would key the cache finer than a
    # station's own catchment, so two clicks on the same street would both pay
    # for the same reading.
    cache_key = f"aqi:{latitude:.3f}:{longitude:.3f}"
    reading = _cache.get(cache_key)
    if reading is None:
        try:
            payload = await fetch_json(
                f"{settings.waqi_api_url}/geo:{latitude};{longitude}/",
                provider=PROVIDER,
                params={"token": settings.waqi_api_token},
                # Safe: this is a read. WAQI's quota is 1,000 requests per
                # second, so one repeat costs nothing worth counting.
                retries=1,
            )
        except TilikError as exc:
            logger.warning("Air quality degraded at %s,%s: %s", latitude, longitude, exc)
            return _unavailable(
                "The air-quality service didn't answer, so there is no reading here."
            )

        reading = parse_feed(payload, latitude, longitude)
        _cache.set(cache_key, reading)

    if reading.status != "ok":
        return _degraded(reading)

    return (
        reading,
        DataSource(
            field="airQuality",
            provider=PROVIDER,
            # A station beyond the configured reach is a real measurement of
            # somewhere else, which is an estimate for here.
            quality="live" if reading.confidence in ("high", "medium") else "estimate",
            note=(
                None
                if reading.confidence == "high"
                else "Read at the nearest station, not at this point."
            ),
        ),
    )
