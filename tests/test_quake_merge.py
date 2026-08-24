"""One earthquake, counted once — without losing any district's dead.

The same shock reaches the list from two directions. USGS publishes the event:
magnitude, depth, intensity, a measured epicentre, a permanent URL. DIBI
publishes what it did, once per affected district. Yogyakarta 2006 therefore
arrives as four rows — `10 km E of Pundong M6.3` from USGS, and Bantul with
4,143 dead, Kota Yogyakarta with 218 and Sleman with 243 from DIBI.

The three DIBI rows are not duplicates of each other: each is a different
district's toll, and collapsing them would discard 461 deaths. The USGS row is a
duplicate of all three. So it is absorbed, its readings copied onto them, and
the shock counted once.
"""

from __future__ import annotations

from api.schemas.location import DisasterEvent, DisasterImpact
from api.services import disasters as disasters_service
from api.services.disasters import SAME_QUAKE_HOURS, _merge_matched_quakes


def loss(identifier: str, area: str, when: str, deaths: int) -> DisasterEvent:
    """A DIBI row: knows the damage, has no seismic reading and no coordinate."""
    return DisasterEvent(
        id=identifier,
        type="earthquake",
        area_name=area,
        title=f"Earthquake — {area}",
        occurred_at=when,
        impact=DisasterImpact(deaths=deaths),
        source="BNPB DIBI (DesInventar)",
        scope="regional",
        distance_meters=0.0,
    )


def shock(identifier: str, when: str, magnitude: float) -> DisasterEvent:
    """A USGS row: knows the shock, has no idea what it cost."""
    return DisasterEvent(
        id=identifier,
        type="earthquake",
        title="10 km E of Pundong, Indonesia",
        occurred_at=when,
        magnitude=magnitude,
        magnitude_scale="mw",
        depth_km=12.5,
        intensity_mmi=7.6,
        intensity_basis="modelled",
        felt_reports=430,
        url="https://earthquake.usgs.gov/earthquakes/eventpage/usp000ejhx",
        source="USGS",
        scope="point",
        distance_meters=15_600.0,
    )


#: DIBI dates in local time, USGS in UTC — the same shock, two calendar days.
YOGYA_LOCAL = "2006-05-27T00:00:00+00:00"
YOGYA_UTC = "2006-05-26T22:53:00+00:00"


class TestMerge:
    def test_the_measured_row_is_absorbed(self) -> None:
        merged = _merge_matched_quakes(
            [loss("bantul", "Bantul", YOGYA_LOCAL, 4143), shock("usgs", YOGYA_UTC, 6.3)]
        )
        assert [e.id for e in merged] == ["bantul"]

    def test_the_loss_row_gains_the_seismic_reading(self) -> None:
        merged = _merge_matched_quakes(
            [loss("bantul", "Bantul", YOGYA_LOCAL, 4143), shock("usgs", YOGYA_UTC, 6.3)]
        )
        row = merged[0]
        assert row.magnitude == 6.3
        assert row.depth_km == 12.5
        assert row.intensity_mmi == 7.6
        # And the URL, which no DIBI row has of its own — DesInventar publishes
        # no per-record page at all.
        assert row.url is not None
        # Its own figure survives untouched.
        assert row.impact is not None and row.impact.deaths == 4143

    def test_every_district_keeps_its_own_dead(self) -> None:
        """Collapsing the three into one would silently drop 461 deaths."""
        merged = _merge_matched_quakes(
            [
                loss("bantul", "Bantul", YOGYA_LOCAL, 4143),
                loss("yogya", "Kota Yogyakarta", YOGYA_LOCAL, 218),
                loss("sleman", "Sleman", YOGYA_LOCAL, 243),
                shock("usgs", YOGYA_UTC, 6.3),
            ]
        )
        tolls = sorted(e.impact.deaths for e in merged if e.impact)
        assert tolls == [218, 243, 4143]
        assert all(e.magnitude == 6.3 for e in merged)

    def test_a_local_date_still_matches_a_utc_one(self) -> None:
        """Yogyakarta 2006 is 26 May to USGS and 27 May to DIBI.

        A same-day join missed it entirely, and with it the 5,188 deaths across
        Bantul, Kota Yogyakarta, Sleman and Klaten.
        """
        assert SAME_QUAKE_HOURS > 24
        merged = _merge_matched_quakes(
            [loss("bantul", "Bantul", YOGYA_LOCAL, 4143), shock("usgs", YOGYA_UTC, 6.3)]
        )
        assert len(merged) == 1

    def test_aftershocks_stay_their_own_events(self) -> None:
        """Only the main shock is the one the damage belongs to.

        27 May 2006 also brought M4.8 and M4.6. Those are separate earthquakes,
        not duplicates, so absorbing them would delete real records.
        """
        merged = _merge_matched_quakes(
            [
                loss("bantul", "Bantul", YOGYA_LOCAL, 4143),
                shock("main", YOGYA_UTC, 6.3),
                shock("after-1", "2006-05-27T05:00:00+00:00", 4.8),
                shock("after-2", "2006-05-27T09:00:00+00:00", 4.6),
            ]
        )
        assert sorted(e.id for e in merged) == ["after-1", "after-2", "bantul"]

    def test_an_unmatched_shock_is_left_alone(self) -> None:
        merged = _merge_matched_quakes(
            [
                loss("bantul", "Bantul", YOGYA_LOCAL, 4143),
                shock("elsewhere", "2015-03-01T00:00:00+00:00", 5.9),
            ]
        )
        assert sorted(e.id for e in merged) == ["bantul", "elsewhere"]

    def test_it_never_overwrites_what_a_row_already_knows(self) -> None:
        """Only gaps are filled, so a real reading is never replaced."""
        row = loss("bantul", "Bantul", YOGYA_LOCAL, 4143)
        row.magnitude = 6.0
        row.magnitude_scale = "m"
        merged = _merge_matched_quakes([row, shock("usgs", YOGYA_UTC, 6.3)])
        assert merged[0].magnitude == 6.0
        assert merged[0].magnitude_scale == "m"
        # The gap it did have is still filled.
        assert merged[0].depth_km == 12.5

    def test_non_quake_rows_are_untouched(self) -> None:
        flood = DisasterEvent(
            id="flood",
            type="flood",
            area_name="Bantul",
            title="Flood — Bantul",
            occurred_at=YOGYA_LOCAL,
            source="BNPB DIBI (DesInventar)",
            scope="regional",
        )
        merged = _merge_matched_quakes([flood, shock("usgs", YOGYA_UTC, 6.3)])
        assert sorted(e.id for e in merged) == ["flood", "usgs"]
        assert merged[0].magnitude is None or merged[0].id != "flood"


class TestCauseIsSearchedWidely:
    """The shock that caused a district's loss need not be near the pin.

    Palu 2018 is the case that forced this apart. The M7.5 that killed 3,624
    people in Kota Palu had its epicentre 72 km north — outside any 25 km search
    — so matching within the display radius found only the M5.8 aftershock
    16 km away and credited it with every death. "M5.8 killed 3,624" is a
    confidently wrong claim, and worse than saying nothing.

    So the cause is looked up separately and widely, and a cause found that way
    lends its readings without ever being listed itself.
    """

    def test_the_search_is_wider_than_any_display_radius(self) -> None:
        from api.services.disasters import SHOCK_SEARCH_KM

        # Palu's mainshock sat 72 km out; the default display radius is 50 km.
        assert SHOCK_SEARCH_KM >= 200

    def test_the_mainshock_wins_over_a_nearer_aftershock(self) -> None:
        palu = loss("palu", "Kota Palu", "2018-09-28T00:00:00+00:00", 3624)
        aftershock = shock("after", "2018-09-28T10:25:04+00:00", 5.8)
        aftershock.distance_meters = 16_000.0
        mainshock = shock("main", "2018-09-28T10:02:45+00:00", 7.5)
        mainshock.distance_meters = 72_000.0

        merged = _merge_matched_quakes([palu, aftershock], shocks=[mainshock])
        row = next(e for e in merged if e.id == "palu")

        assert row.magnitude == 7.5
        assert row.impact is not None and row.impact.deaths == 3624

    def test_a_cause_from_the_wide_search_is_not_listed(self) -> None:
        """It was never on screen, so absorbing it must not add a row."""
        palu = loss("palu", "Kota Palu", "2018-09-28T00:00:00+00:00", 3624)
        mainshock = shock("main", "2018-09-28T10:02:45+00:00", 7.5)

        merged = _merge_matched_quakes([palu], shocks=[mainshock])
        assert [e.id for e in merged] == ["palu"]

    def test_a_listed_shock_is_still_absorbed(self) -> None:
        """One already on screen must not be doubled by the loss row."""
        bantul = loss("bantul", "Bantul", "2006-05-27T00:00:00+00:00", 4143)
        listed = shock("listed", "2006-05-26T22:53:00+00:00", 6.3)

        merged = _merge_matched_quakes([bantul, listed], shocks=[listed])
        assert [e.id for e in merged] == ["bantul"]


class TestOnlyMeaningfulLossMerges:
    """A record with nothing recorded is left unpaired.

    Bogor's earthquake of 2012 lists no casualties and no displacement. Merging
    it contributed an area name and cost the measured epicentre it replaced —
    and because the merged row is area-bound, it then competed under the
    per-area cap and lost its slot, so the event vanished from the list
    altogether. Worse than not merging.
    """

    def test_an_empty_loss_record_does_not_absorb(self) -> None:
        empty = loss("bogor", "Bogor", YOGYA_LOCAL, 0)
        assert empty.impact is not None and empty.impact.deaths == 0

        merged = _merge_matched_quakes([empty, shock("usgs", YOGYA_UTC, 6.3)])

        # The measured row survives, and keeps its own identity.
        assert sorted(e.id for e in merged) == ["bogor", "usgs"]
        assert next(e for e in merged if e.id == "bogor").magnitude is None

    def test_a_loss_record_with_no_impact_block_does_not_absorb(self) -> None:
        bare = loss("bare", "Somewhere", YOGYA_LOCAL, 0)
        bare.impact = None

        merged = _merge_matched_quakes([bare, shock("usgs", YOGYA_UTC, 6.3)])
        assert sorted(e.id for e in merged) == ["bare", "usgs"]

    def test_harm_other_than_death_still_counts(self) -> None:
        """Displacement or destroyed houses make a record worth pairing."""
        from api.schemas.location import DisasterImpact

        row = loss("row", "Somewhere", YOGYA_LOCAL, 0)
        row.impact = DisasterImpact(deaths=0, displaced=5_071)

        merged = _merge_matched_quakes([row, shock("usgs", YOGYA_UTC, 6.3)])
        assert [e.id for e in merged] == ["row"]
        assert merged[0].magnitude == 6.3


class TestTsunamiMerge:
    """One wave must not be listed twice, and no district may be given a height
    that was measured somewhere else.

    Palu 2018 reaches the list from both directions: NOAA/NCEI observed 10.73 m
    at a measured place, and DIBI recorded 3,624 deaths for Kota Palu. Aceh 2004
    arrives as a 50.9 m observation plus loss records for both Kota Banda Aceh
    and Kota Sabang, 24 km apart.
    """

    @staticmethod
    def _runup(**overrides) -> DisasterEvent:
        row = {
            "id": "ncei-1",
            "type": "tsunami",
            "hazard_types": ["tsunami"],
            "title": "Palu City",
            "source": "NOAA NCEI (tsunami runups)",
            "occurred_at": "2018-09-28T10:02:45+00:00",
            "scope": "point",
            "distance_meters": 1_500.0,
            "distance_basis": "measured",
            "water_height_m": 10.73,
        }
        row.update(overrides)
        return DisasterEvent(**row)

    @staticmethod
    def _loss(**overrides) -> DisasterEvent:
        row = {
            "id": "desinventar-1",
            "type": "earthquake and tsunami",
            "hazard_types": ["earthquake", "tsunami"],
            "title": "Kota Palu",
            "source": "BNPB DIBI (DesInventar)",
            "occurred_at": "2018-09-28T00:00:00+00:00",
            "scope": "regional",
            "distance_meters": 0.0,
            "impact": DisasterImpact(deaths=3624),
        }
        row.update(overrides)
        return DisasterEvent(**row)

    def test_the_wave_is_listed_once_carrying_both_figures(self) -> None:
        merged = disasters_service._merge_matched_tsunamis(
            [self._runup(), self._loss()]
        )

        assert len(merged) == 1
        # The toll DIBI recorded and the height NCEI measured, on one row.
        assert merged[0].impact.deaths == 3624
        assert merged[0].water_height_m == 10.73

    def test_only_the_nearest_district_gains_the_height(self) -> None:
        """Aceh's 50.9 m was measured near Banda Aceh, not at Sabang.

        Copying it onto every district in range would invent a local figure the
        database never recorded there.
        """
        banda = self._loss(id="desinventar-1", title="Kota Banda Aceh", distance_meters=0.0)
        sabang = self._loss(id="desinventar-2", title="Kota Sabang", distance_meters=24_600.0)

        merged = disasters_service._merge_matched_tsunamis(
            [self._runup(water_height_m=50.9), banda, sabang]
        )

        assert len(merged) == 2
        by_title = {event.title: event for event in merged}
        assert by_title["Kota Banda Aceh"].water_height_m == 50.9
        assert by_title["Kota Sabang"].water_height_m is None

    def test_an_unmatched_observation_stands_on_its_own(self) -> None:
        """Krakatoa 1883 has no DIBI record. It is still the row that matters."""
        krakatoa = self._runup(
            id="ncei-2",
            title="Batavia, Java",
            occurred_at="1883-08-27T00:00:00+00:00",
            water_height_m=2.58,
        )

        merged = disasters_service._merge_matched_tsunamis([krakatoa])

        assert merged == [krakatoa]

    def test_a_loss_record_with_no_harm_absorbs_nothing(self) -> None:
        """Otherwise an empty district row swallows a measured observation."""
        empty = self._loss(impact=None)
        runup = self._runup()

        merged = disasters_service._merge_matched_tsunamis([runup, empty])

        assert {event.id for event in merged} == {"ncei-1", "desinventar-1"}
