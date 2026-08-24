"""Tsunami rows must say where the water reached, and how high.

NOAA/NCEI publishes two tables and only one answers this section's question.
`events` holds one row per tsunami at its *source* — 250 km off Aceh for 2004 —
so a plot in Banda Aceh would read as 250 km from the wave that destroyed it.
`runups` holds one row per observation, at a measured place, with the height the
water reached there. This module reads runups, and these tests pin the two
decisions that make the difference between a useful figure and a dangerous one.
"""

from __future__ import annotations

import asyncio

import pytest

from api.services import ncei_tsunami


def runup(**overrides) -> dict:
    """One NCEI runup row, shaped like the live API's."""
    row = {
        "id": 33094,
        "tsunamiEventId": 5689,
        "year": 2018,
        "month": 9,
        "day": 28,
        "hour": 10,
        "minute": 2,
        "second": 45.3,
        "country": "INDONESIA",
        "locationName": "PALU",
        "latitude": -0.88,
        "longitude": 119.837,
        "runupHt": 3.0,
        "doubtful": "n",
        "publish": True,
    }
    row.update(overrides)
    return row


def fetch(monkeypatch: pytest.MonkeyPatch, rows: list[dict], **kwargs):
    """Run the fetcher against a fixed page of rows."""

    async def _stub(url, **_):
        return {"items": rows}

    monkeypatch.setattr(ncei_tsunami, "fetch_json", _stub)
    return asyncio.run(
        ncei_tsunami.fetch_runups(
            kwargs.get("latitude", -0.8990),
            kwargs.get("longitude", 119.8707),
            kwargs.get("radius_meters", 25_000),
            kwargs.get("years", 200),
        )
    )


class TestHeight:
    def test_reports_the_highest_observation_not_the_nearest(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The closest reading is often a tide gauge, and gauges read low.

        Within 25 km of Banda Aceh the 2004 tsunami has observations from 2.1 m
        to 50.9 m, and the one nearest the city centre is 0.6 m. A row saying
        the 2004 tsunami reached 0.6 m here would be the most misleading figure
        in the section, so the height is the highest within the radius even when
        it was measured further out than the nearest reading.
        """
        events = fetch(
            monkeypatch,
            [
                # Nearest to the pin, and lowest.
                runup(id=1, latitude=-0.8995, longitude=119.8710, runupHt=0.6),
                runup(id=2, latitude=-0.88, longitude=119.837, runupHt=50.9),
            ],
        )

        assert len(events) == 1
        assert events[0].water_height_m == 50.9

    def test_keeps_a_row_with_no_height_at_all(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """About one runup in a hundred has no height. It still happened."""
        events = fetch(monkeypatch, [runup(runupHt=None)])

        assert len(events) == 1
        assert events[0].water_height_m is None


class TestPosition:
    def test_the_distance_is_to_the_nearest_observation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An observation is a measured place, so its distance is a real one."""
        events = fetch(
            monkeypatch,
            [
                runup(id=1, latitude=-0.8995, longitude=119.8710, runupHt=0.6),
                runup(id=2, latitude=-0.88, longitude=119.837, runupHt=50.9),
            ],
        )

        assert events[0].distance_basis == "measured"
        assert events[0].scope == "point"
        # The nearer of the two, not the one the height came from.
        assert events[0].distance_meters < 1_000

    def test_drops_observations_outside_the_radius(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The bounding box is wider than the circle, so it must be re-filtered."""
        events = fetch(
            monkeypatch,
            [runup(latitude=-0.6, longitude=119.6)],
            radius_meters=5_000,
        )

        assert events == []


class TestOneRowPerWave:
    def test_a_mega_event_contributes_one_row(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Palu 2018 has 195 observations within 25 km. It is one tsunami."""
        rows = [
            runup(id=index, latitude=-0.88 - index / 10_000, runupHt=index / 10)
            for index in range(1, 40)
        ]

        events = fetch(monkeypatch, rows)

        assert len(events) == 1

    def test_separate_waves_stay_separate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        events = fetch(
            monkeypatch,
            [
                runup(id=1, tsunamiEventId=5689, year=2018),
                runup(id=2, tsunamiEventId=613, year=1927),
            ],
        )

        assert len(events) == 2


class TestExclusions:
    @pytest.mark.parametrize(
        "overrides",
        [
            pytest.param({"doubtful": "y"}, id="doubtful"),
            pytest.param({"publish": False}, id="withheld"),
            pytest.param({"latitude": None}, id="no-position"),
            pytest.param({"year": None}, id="no-year"),
        ],
    )
    def test_rows_the_database_itself_qualifies_are_dropped(
        self, monkeypatch: pytest.MonkeyPatch, overrides: dict
    ) -> None:
        assert fetch(monkeypatch, [runup(**overrides)]) == []


class TestDates:
    def test_a_year_only_record_still_counts(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Older runups carry no month, day or time. 1883 is still 1883."""
        events = fetch(
            monkeypatch,
            [runup(year=1883, month=None, day=None, hour=None, minute=None, second=None)],
        )

        assert events[0].occurred_at.startswith("1883-01-01")

    def test_an_impossible_date_falls_back_to_the_year(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """NCEI holds a few Feb-30s. Discarding the row would lose a tsunami."""
        events = fetch(monkeypatch, [runup(year=1861, month=2, day=30)])

        assert events[0].occurred_at.startswith("1861-01-01")


class TestYearWindow:
    def test_the_window_is_enforced_here_not_by_the_api(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`minYear` is accepted by the runups endpoint and then ignored.

        Asking for 2001 onwards in a box around Banda Aceh returns 200 rows
        whose oldest is 1861. Trusting the parameter put an 1885 tsunami into a
        search captioned "last 25 years".
        """
        events = fetch(
            monkeypatch,
            [
                runup(id=1, tsunamiEventId=10, year=1885),
                runup(id=2, tsunamiEventId=20, year=2018),
            ],
            years=25,
        )

        assert [event.occurred_at[:4] for event in events] == ["2018"]

    def test_a_wider_window_lets_the_old_ones_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        events = fetch(
            monkeypatch,
            [runup(id=1, tsunamiEventId=10, year=1885)],
            years=200,
        )

        assert len(events) == 1
