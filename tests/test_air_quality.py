"""WAQI banding, parsing and the four ways this section can come back empty.

Two things here are not hypothetical and are the reason the module is shaped
the way it is.

* **WAQI reports failure with HTTP 200.** A bad token is
  ``{"status": "error", "data": "Invalid key"}``; no nearby monitor is
  ``{"status": "nug", ...}``. Both decode as valid JSON, so nothing upstream of
  ``parse_feed`` can tell them from a reading. Trusted, a misconfigured
  deployment would report clean air for every plot in Indonesia.
* **The ``demo`` token answers Shanghai for every coordinate on earth.** Asked
  about Jakarta it returns a real, plausible, wrong reading 4,440 km away, which
  is why the station distance is computed here rather than trusted from the
  payload, and why it sets the confidence.

No network. ``parse_feed`` is pure, and the gates in front of it are checked by
proving ``fetch_json`` is never reached.
"""

from __future__ import annotations

import asyncio

import pytest

from api.core.config import Settings
from api.services import air_quality as air_quality_service
from api.services.air_quality import (
    ANOTHER_REGION_METERS,
    AT_POINT_METERS,
    classify_aqi,
    confidence_for,
    parse_feed,
)

#: A real WAQI body, captured from `/feed/geo:-6.2088;106.8456/?token=demo`.
#: Kept whole, weather keys included, because dropping the weather would remove
#: the thing one of these tests is about.
PAYLOAD = {
    "status": "ok",
    "data": {
        "aqi": 46,
        "idx": 1437,
        "attributions": [
            {"url": "https://sthj.sh.gov.cn/", "name": "Shanghai Environment Monitoring Center"},
            {"url": "https://waqi.info/", "name": "World Air Quality Index Project"},
        ],
        "city": {
            "geo": [31.2047372, 121.4489017],
            "name": "Shanghai",
            "url": "https://aqicn.org/city/shanghai",
            "location": "",
        },
        "dominentpol": "pm25",
        "iaqi": {
            "co": {"v": 7.3},
            "h": {"v": 73},
            "no2": {"v": 11.5},
            "o3": {"v": 26.4},
            "p": {"v": 1010},
            "pm10": {"v": 20},
            "pm25": {"v": 46},
            "so2": {"v": 3.6},
            "t": {"v": 25.5},
            "w": {"v": 3.6},
        },
        "time": {"iso": "2026-09-08T07:00:00+08:00", "tz": "+08:00", "v": 1788850800},
    },
}

#: Monas, Jakarta. The captured payload's own station is in Shanghai, 4,440 km
#: away, which is deliberate: that is what the `demo` token really answers for
#: this coordinate, and it is now past the useful-range cutoff.
JAKARTA = (-6.2088, 106.8456)

#: Stations placed to sit in each band the two thresholds create.
#: `AT_POINT_METERS` is 5 km and `waqi_max_station_meters` 25 km, so: under 1 km,
#: about 9 km, and about 33 km. Beyond 50 km is `PAYLOAD` itself.
AT_DOORSTEP = [-6.21, 106.8456]
SAME_CITY = [-6.29, 106.8456]
NEXT_TOWN = [-6.51, 106.8456]


def _near(latitude: float, longitude: float, *, station: list[float]) -> dict:
    """The captured payload, moved to a station at a chosen coordinate."""
    payload = {"status": "ok", "data": dict(PAYLOAD["data"])}
    payload["data"]["city"] = dict(PAYLOAD["data"]["city"]) | {"geo": station}
    return payload


#: The ordinary case: a real station in the same city as the checked point.
IN_RANGE = _near(*JAKARTA, station=SAME_CITY)


class TestClassify:
    @pytest.mark.parametrize(
        ("aqi", "band", "level"),
        [
            (0, "good", "low"),
            (50, "good", "low"),
            (51, "moderate", "low"),
            (100, "moderate", "low"),
            (101, "unhealthySensitive", "medium"),
            (150, "unhealthySensitive", "medium"),
            (151, "unhealthy", "high"),
            (200, "unhealthy", "high"),
            (201, "veryUnhealthy", "high"),
            (300, "veryUnhealthy", "high"),
            (301, "hazardous", "high"),
            (999, "hazardous", "high"),
        ],
    )
    def test_every_epa_boundary(self, aqi: int, band: str, level: str):
        """The published breakpoints, inclusive at the top of each band."""
        got_band, label, got_level = classify_aqi(aqi)
        assert (got_band, got_level) == (band, level)
        assert label

    def test_no_reading_is_not_a_good_reading(self):
        """A missing index must never band as clean air."""
        assert classify_aqi(None) == ("unknown", "Unknown", "unknown")

    def test_moderate_stays_off_the_hazard_colour(self):
        """AQI 60 shares a palette with a high tsunami index if this regresses."""
        _, _, level = classify_aqi(60)
        assert level == "low"


class TestConfidence:
    @pytest.mark.parametrize(
        ("metres", "expected"),
        [
            (0, "high"),
            (AT_POINT_METERS, "high"),
            (AT_POINT_METERS + 1, "medium"),
            (15_000, "medium"),
            (25_000, "medium"),
            (25_001, "low"),
            (60_000, "low"),
        ],
    )
    def test_distance_decides_what_the_reading_describes(self, metres: int, expected: str):
        assert confidence_for(metres) == expected

    def test_an_unknown_distance_claims_nothing(self):
        assert confidence_for(None) == "none"


class TestParseReading:
    def test_reads_the_headline_figure_and_its_driver(self):
        air = parse_feed(IN_RANGE, *JAKARTA)

        assert air.status == "ok"
        assert air.aqi == 46
        assert (air.band, air.band_label, air.level) == ("good", "Good", "low")
        assert air.dominant_pollutant == "pm25"
        assert air.dominant_label == "PM2.5"
        assert air.measured_at == "2026-09-08T07:00:00+08:00"

    def test_every_pollutant_carries_its_published_band_name(self):
        """The table's Status column prints this. Derived in the UI it would
        put the EPA's wording in two places."""
        air = parse_feed(
            _near(*JAKARTA, station=SAME_CITY)
            | {
                "data": dict(PAYLOAD["data"])
                | {
                    "city": dict(PAYLOAD["data"]["city"]) | {"geo": SAME_CITY},
                    "iaqi": {"pm25": {"v": 152}, "pm10": {"v": 120}, "o3": {"v": 31}},
                }
            },
            *JAKARTA,
        )

        assert [(p.label, p.band_label) for p in air.pollutants] == [
            ("PM2.5", "Unhealthy"),
            ("PM10", "Unhealthy for sensitive groups"),
            ("Ozone (O3)", "Good"),
        ]

    def test_marks_the_dominant_pollutant_and_only_that_one(self):
        air = parse_feed(IN_RANGE, *JAKARTA)
        dominant = [reading.key for reading in air.pollutants if reading.dominant]
        assert dominant == ["pm25"]

    def test_weather_is_not_pollution(self):
        """`iaqi` carries t/h/p/w. Listed, 25.5 degrees reads as an AQI of 25.5."""
        air = parse_feed(IN_RANGE, *JAKARTA)
        keys = [reading.key for reading in air.pollutants]

        assert keys == ["pm25", "pm10", "o3", "no2", "so2", "co"]
        assert not {"t", "h", "p", "w"} & set(keys)

    def test_computes_the_station_distance_waqi_never_sends(self):
        air = parse_feed(IN_RANGE, *JAKARTA)

        assert air.station_distance_meters is not None
        assert 8_000 < air.station_distance_meters < 10_000

    def test_a_station_on_the_doorstep_is_a_measurement_here(self):
        air = parse_feed(_near(*JAKARTA, station=AT_DOORSTEP), *JAKARTA)

        assert air.station_distance_meters is not None
        assert air.station_distance_meters < AT_POINT_METERS
        assert air.confidence == "high"

    def test_a_station_in_the_next_town_still_reports_its_figure(self):
        """Inside the cutoff, so the number is kept and the claim demoted."""
        air = parse_feed(_near(*JAKARTA, station=NEXT_TOWN), *JAKARTA)

        assert air.status == "ok"
        assert air.aqi == 46
        assert air.confidence == "low"

    def test_keeps_the_attributions_the_licence_requires(self):
        air = parse_feed(IN_RANGE, *JAKARTA)
        names = [credit.name for credit in air.attributions]

        assert "World Air Quality Index Project" in names
        assert all(credit.url for credit in air.attributions)

    def test_counts_what_the_index_is_built_from(self):
        """The table needs a denominator. BMKG stations mostly report one."""
        air = parse_feed(IN_RANGE, *JAKARTA)

        assert air.pollutants_possible == 6

    def test_claims_no_comparison_where_one_pollutant_was_measured(self):
        """"PM2.5 is the pollutant setting it" implies it beat the others.

        Kemayoran reports PM2.5 and weather, nothing else, so the headline
        figure is simply PM2.5's own number and there was no contest to win.
        """
        one = {
            "status": "ok",
            "data": dict(PAYLOAD["data"])
            | {
                "city": dict(PAYLOAD["data"]["city"]) | {"geo": SAME_CITY},
                "iaqi": {"pm25": {"v": 152}, "t": {"v": 28}},
            },
        }
        air = parse_feed(one, *JAKARTA)

        assert len(air.pollutants) == 1
        assert "setting it" not in air.description
        assert "the only pollutant this station measures" in air.description

    def test_still_names_the_driver_where_there_were_rivals(self):
        many = {
            "status": "ok",
            "data": dict(PAYLOAD["data"])
            | {
                "city": dict(PAYLOAD["data"]["city"]) | {"geo": SAME_CITY},
                "iaqi": {"pm25": {"v": 152}, "pm10": {"v": 120}, "o3": {"v": 31}},
            },
        }
        air = parse_feed(many, *JAKARTA)

        assert len(air.pollutants) == 3
        assert "PM2.5 is the pollutant setting it" in air.description

    def test_the_distance_clause_fits_the_range_it_can_receive(self):
        """This branch only ever sees 25 to 50 km now, so it must not overstate.

        It once had to describe the `demo` token's station 4,440 km away and
        said the figure "may not describe the air here at all", which was true
        of Shanghai and far too strong for the next kabupaten.
        """
        air = parse_feed(_near(*JAKARTA, station=NEXT_TOWN), *JAKARTA)

        assert "describes the region rather than this address" in air.description
        assert "may not describe the air here at all" not in air.description

    def test_says_where_the_reading_came_from(self):
        far = parse_feed(_near(*JAKARTA, station=NEXT_TOWN), *JAKARTA).description
        near = parse_feed(_near(*JAKARTA, station=AT_DOORSTEP), *JAKARTA).description

        assert "describes the region rather than this address" in far
        assert "close enough to describe this point" in near
        # An AQI is an hour, and the copy has to say so either way.
        assert "not a pattern" in far
        assert "not a pattern" in near

    def test_a_station_with_no_geo_claims_no_distance(self):
        # No distance means no cutoff test is possible, so the reading stands.
        payload = {"status": "ok", "data": dict(PAYLOAD["data"]) | {"city": {"name": "Somewhere"}}}
        air = parse_feed(payload, *JAKARTA)

        assert air.status == "ok"
        assert air.station_distance_meters is None
        assert air.confidence == "none"


class TestDistanceNeverSuppresses:
    """A far station's reading is shown, with its distance. Always.

    A cutoff was tried here and removed. With 25 BMKG stations covering
    Indonesia, suppressing readings past 50 km left Surabaya, Bandung, Denpasar
    and Balikpapan with a blank section, and the operator's call is that a
    distant reading shown with its distance beats no reading at all.

    What distance changes is the wording and the confidence. These tests pin
    that it changes nothing else, because the temptation to reintroduce a cutoff
    is exactly what produced the blank sections.
    """

    def test_a_station_on_the_other_side_of_asia_still_reports(self):
        # The captured payload's own station: Shanghai, 4,440 km from Jakarta.
        air = parse_feed(PAYLOAD, *JAKARTA)

        assert air.status == "ok"
        assert air.aqi == 46
        assert air.pollutants
        assert air.station_distance_meters is not None
        assert 4_400_000 < air.station_distance_meters < 4_500_000

    @pytest.mark.parametrize("degrees", [0.1, 0.3, 0.6, 1.1, 4.0])
    def test_no_distance_turns_a_reading_into_a_gap(self, degrees: float):
        air = parse_feed(
            _near(*JAKARTA, station=[JAKARTA[0] - degrees, JAKARTA[1]]), *JAKARTA
        )

        assert air.status == "ok"
        assert air.aqi is not None

    def test_distance_shows_up_as_confidence_instead(self):
        """The claim is demoted rather than withheld."""
        bands = [
            (AT_DOORSTEP, "high"),
            (SAME_CITY, "medium"),
            (NEXT_TOWN, "low"),
        ]
        for station, expected in bands:
            air = parse_feed(_near(*JAKARTA, station=station), *JAKARTA)
            assert air.confidence == expected, station

        # And the far payload, which no band above reaches.
        assert parse_feed(PAYLOAD, *JAKARTA).confidence == "low"

    def test_the_wording_stops_calling_the_far_ones_this_region(self):
        """"The region" is false for Bandung's Jakarta station, and for Shanghai."""
        region = parse_feed(_near(*JAKARTA, station=NEXT_TOWN), *JAKARTA)
        elsewhere = parse_feed(PAYLOAD, *JAKARTA)

        assert "describes the region rather than this address" in region.description

        assert "another part of the country" in elsewhere.description
        assert "the region" not in elsewhere.description
        assert "this area" not in elsewhere.description

    def test_the_wording_boundary(self):
        """100 km is where "region" gives way to "elsewhere"."""
        # 0.85 degrees of latitude is about 94 km; 0.95 is about 105 km.
        near = parse_feed(_near(*JAKARTA, station=[JAKARTA[0] - 0.85, JAKARTA[1]]), *JAKARTA)
        far = parse_feed(_near(*JAKARTA, station=[JAKARTA[0] - 0.95, JAKARTA[1]]), *JAKARTA)

        assert near.station_distance_meters is not None
        assert near.station_distance_meters < ANOTHER_REGION_METERS
        assert "describes the region" in near.description

        assert far.station_distance_meters is not None
        assert far.station_distance_meters > ANOTHER_REGION_METERS
        assert "another part of the country" in far.description


class TestProvenance:
    """What the report's gaps notice is told, which is not the same as status."""

    def test_no_station_is_not_a_provider_failure(self):
        """WAQI answered. Filed as unavailable it would report an outage."""
        reading = parse_feed({"status": "nug", "data": "Unknown station"}, *JAKARTA)
        _, source = air_quality_service._degraded(reading)

        assert reading.status == "no_station"
        assert source.quality == "live"

    @pytest.mark.parametrize("status", ["unavailable", "not_configured", "disabled"])
    def test_everything_else_is(self, status: str):
        from api.schemas.location import AirQuality

        _, source = air_quality_service._degraded(
            AirQuality(status=status, description="x", note="x")  # type: ignore[arg-type]
        )

        assert source.quality == "unavailable"


class TestParseFailures:
    """Every one of these arrives as HTTP 200 with a valid JSON body."""

    def test_no_monitor_here_is_a_coverage_gap_not_clean_air(self):
        air = parse_feed({"status": "nug", "data": "Unknown station"}, *JAKARTA)

        assert air.status == "no_station"
        assert air.aqi is None
        assert air.level == "unknown"
        assert air.note and "not clean air" in air.note

    def test_a_rejected_token_is_our_problem_and_says_so(self):
        air = parse_feed({"status": "error", "data": "Invalid key"}, *JAKARTA)

        assert air.status == "unavailable"
        assert air.note and "setup problem on our side" in air.note

    def test_a_station_reporting_a_dash_has_no_reading(self):
        """WAQI sends "-" for a monitor that is online but silent."""
        air = parse_feed({"status": "ok", "data": {"aqi": "-", "city": {}}}, *JAKARTA)

        assert air.status == "no_station"
        assert air.aqi is None

    @pytest.mark.parametrize("payload", ["not json", None, [], {"status": "ok", "data": None}])
    def test_a_shape_we_cannot_read_never_raises(self, payload):
        air = parse_feed(payload, *JAKARTA)

        assert air.status in ("unavailable", "no_station")
        assert air.aqi is None
        assert air.description


class TestGates:
    """What must happen before any coordinate leaves this machine."""

    def _run(self, monkeypatch: pytest.MonkeyPatch, **overrides):
        settings = Settings(**overrides)
        monkeypatch.setattr(air_quality_service, "get_settings", lambda: settings)

        reached = []

        async def never(*args, **kwargs):
            reached.append(kwargs.get("provider"))
            raise AssertionError("the gate let a request through")

        monkeypatch.setattr(air_quality_service, "fetch_json", never)
        air_quality_service._cache.clear()

        air, source = asyncio.run(air_quality_service.get_air_quality(*JAKARTA))
        return air, source, reached

    def test_no_token_reports_itself_rather_than_calling(self, monkeypatch):
        air, source, reached = self._run(monkeypatch, waqi_api_token=None)

        assert air.status == "not_configured"
        assert source.quality == "unavailable"
        assert reached == []

    def test_turned_off_is_distinct_from_not_configured(self, monkeypatch):
        air, _, reached = self._run(
            monkeypatch, waqi_api_token="a-token", enable_air_quality=False
        )

        assert air.status == "disabled"
        assert reached == []

    def test_offline_mode_makes_no_outbound_call(self, monkeypatch):
        air, _, reached = self._run(
            monkeypatch, waqi_api_token="a-token", enable_external_apis=False
        )

        assert air.status == "unavailable"
        assert reached == []

    def test_the_field_name_matches_the_key_the_ui_looks_up(self, monkeypatch):
        """`ReportGaps` keys its labels on this string, so a rename hides a failure."""
        _, source, _ = self._run(monkeypatch, waqi_api_token=None)

        assert source.field == "airQuality"
        assert source.provider == "waqi"
