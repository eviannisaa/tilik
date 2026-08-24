"""A disaster history should list what reached people, not what reached sensors.

Java sits above a subducting slab that produces a steady stream of magnitude
4–5 earthquakes 130–190 km down. USGS records every one; none is felt at the
surface. Left unfiltered they dominate the section — within 200 km of Serpong a
third of the catalogue is that deep — so a report for a plot of land listed
hundreds of tremors nobody noticed and, because USGS is a seismic network, not
one of the floods that actually flooded the place.

These pin the filter and the magnitude-scale normalisation that goes with it:
the same earthquake is `mb 4.4` to USGS and an unlabelled `4.4` to BMKG, so the
scale has to be stored explicitly for the column to mean anything.
"""

from __future__ import annotations

import asyncio

import pytest

from api.schemas.location import DisasterEvent
from api.services import disasters as disasters_service
from api.services import gdacs
from api.services.disasters import _normalise_scale, _parse_usgs_feature, _was_felt

#: The event behind this whole exercise: USGS first announced it as
#: "0 km NE of Serpong, 4.5 mb", then revised it to 4.4 at 194 km depth, 54 km
#: away. No felt reports, no ShakeMap — nobody experienced it.
DEEP_SLAB_QUAKE = {
    "id": "us6000tlv2",
    "properties": {
        "place": "21 km N of Kresek, Indonesia",
        "mag": 4.4,
        "magType": "mb",
        "time": 1787141942000,
        "felt": None,
        "cdi": None,
        "mmi": None,
        "alert": None,
        "url": "https://earthquake.usgs.gov/earthquakes/eventpage/us6000tlv2",
    },
    "geometry": {"type": "Point", "coordinates": [106.3523, -5.9396, 194.344]},
}

#: Cianjur, 2022 — magnitude 5.6, but 10 km down and over 600 people died.
#: Smaller than the slab event on paper, and the one that mattered.
SHALLOW_DAMAGING_QUAKE = {
    "id": "us7000iu9y",
    "properties": {
        "place": "11 km NE of Sukabumi, Indonesia",
        "mag": 5.6,
        "magType": "mww",
        "time": 1669014000000,
        "felt": 169,
        "cdi": 7.2,
        "mmi": 8.471,
        "alert": "orange",
        "url": "https://earthquake.usgs.gov/earthquakes/eventpage/us7000iu9y",
    },
    "geometry": {"type": "Point", "coordinates": [107.05, -6.84, 10.0]},
}

SERPONG = (-6.31, 106.67)


def parse(feature: dict):
    event = _parse_usgs_feature(feature, *SERPONG)
    assert event is not None
    return event


class TestFeltFilter:
    def test_deep_slab_quake_is_dropped(self) -> None:
        """194 km down with no intensity and no reports: instrument-only."""
        assert _was_felt(parse(DEEP_SLAB_QUAKE), 70.0) is False

    def test_shallow_damaging_quake_is_kept(self) -> None:
        assert _was_felt(parse(SHALLOW_DAMAGING_QUAKE), 70.0) is True

    def test_evidence_of_shaking_outranks_depth(self) -> None:
        """A deep quake that was actually felt stays.

        Depth is only a fallback for when the catalogue says nothing either
        way — a real intensity reading is an observation and must win.
        """
        feature = {
            **DEEP_SLAB_QUAKE,
            "properties": {**DEEP_SLAB_QUAKE["properties"], "mmi": 5.4},
        }
        event = parse(feature)
        assert event.depth_km == 194.3
        assert _was_felt(event, 70.0) is True

    def test_a_single_felt_report_is_enough(self) -> None:
        feature = {
            **DEEP_SLAB_QUAKE,
            "properties": {**DEEP_SLAB_QUAKE["properties"], "felt": 1},
        }
        assert _was_felt(parse(feature), 70.0) is True

    def test_intensity_below_perception_is_not_evidence(self) -> None:
        """MMI I is "not felt" by definition, so it cannot rescue an event."""
        feature = {
            **DEEP_SLAB_QUAKE,
            "properties": {**DEEP_SLAB_QUAKE["properties"], "mmi": 1.0},
        }
        assert _was_felt(parse(feature), 70.0) is False

    def test_unknown_depth_is_kept(self) -> None:
        """Absence of a depth is not evidence of absence of shaking."""
        feature = {
            **DEEP_SLAB_QUAKE,
            "geometry": {"type": "Point", "coordinates": [106.35, -5.94]},
        }
        event = parse(feature)
        assert event.depth_km is None
        assert _was_felt(event, 70.0) is True


class TestIntensity:
    def test_modelled_shakemap_is_preferred_over_reports(self) -> None:
        """`mmi` is computed for every significant event; `cdi` needs a witness.

        Outside the US almost nobody files one — a magnitude 7.7 near Ende drew
        48 reports — so the modelled figure is the one with coverage.
        """
        event = parse(SHALLOW_DAMAGING_QUAKE)
        assert event.intensity_mmi == 8.5
        assert event.intensity_basis == "modelled"

    def test_falls_back_to_reported_intensity(self) -> None:
        feature = {
            **SHALLOW_DAMAGING_QUAKE,
            "properties": {**SHALLOW_DAMAGING_QUAKE["properties"], "mmi": None},
        }
        event = parse(feature)
        assert event.intensity_mmi == 7.2
        assert event.intensity_basis == "reported"

    def test_no_intensity_at_all(self) -> None:
        event = parse(DEEP_SLAB_QUAKE)
        assert event.intensity_mmi is None
        assert event.intensity_basis is None

    def test_pager_alert_becomes_severity(self) -> None:
        assert parse(SHALLOW_DAMAGING_QUAKE).severity == "orange"


class TestMagnitudeScale:
    @pytest.mark.parametrize(
        ("reported", "normalised"),
        [
            ("mb", "mb"),
            # USGS's moment-magnitude flavours differ in method, not in scale.
            ("mww", "mw"),
            ("mwc", "mw"),
            ("Mww", "mw"),
            ("ml", "ml"),
            ("ms20", "ms"),
            # BMKG publishes a bare number and names no scale.
            ("m", "m"),
            ("mint", "other"),
        ],
    )
    def test_normalises_provider_labels(self, reported: str, normalised: str) -> None:
        assert _normalise_scale(reported) == (normalised, reported)

    def test_keeps_the_providers_own_wording(self) -> None:
        """Normalising must not destroy what the source actually said."""
        event = parse(SHALLOW_DAMAGING_QUAKE)
        assert event.magnitude_scale == "mw"
        assert event.magnitude_scale_source == "mww"

    def test_absent_scale_stays_absent(self) -> None:
        """An unlabelled magnitude must not be silently promoted to a scale."""
        assert _normalise_scale(None) == (None, None)
        assert _normalise_scale("  ") == (None, None)

    def test_the_two_agencies_do_not_collide(self) -> None:
        """The whole reason the column was split.

        USGS calls this event `mb`; a BMKG bulletin for the same quake prints
        the number alone. Both are stored, and the normalised values differ, so
        nothing can compare them as if they were one scale.
        """
        usgs = parse(DEEP_SLAB_QUAKE)
        bmkg_scale, bmkg_source = _normalise_scale("M")
        assert usgs.magnitude_scale == "mb"
        assert bmkg_scale == "m"
        assert usgs.magnitude_scale != bmkg_scale


def _archive(monkeypatch: pytest.MonkeyPatch, *hazards: str) -> None:
    """Pin what the imported archive holds, instead of reading a live database.

    Coverage is a property of the catalogue rather than of the rows returned, so
    the service asks the database what it holds. These tests hand their rows in
    directly and must not depend on whether the developer has run an importer.
    """

    async def _stub() -> frozenset[str]:
        return frozenset(hazards)

    monkeypatch.setattr(disasters_service, "_archived_hazards", _stub)


class TestCoveredTypes:
    """`covered_types` is a promise, so it has to list every hazard searched.

    Its contract is that anything absent was never looked for — "no flood
    recorded" must not read as "no flood happened". A stored Palu row labelled
    `earthquake and tsunami` therefore has to register under both names, or the
    section quietly claims tsunami was never searched while holding a
    128,728-death tsunami.
    """

    @staticmethod
    def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
        """Keep the test to stored events by taking the network away."""
        from api.core.config import Settings

        # Pinned, not inherited: `Settings()` reads the developer's `.env`,
        # so an unpinned flag would make these pass or fail by machine.
        settings = Settings(
            enable_external_apis=False,
            disaster_require_measured_location=False,
        )
        monkeypatch.setattr(disasters_service, "get_settings", lambda: settings)
        # No importer has run, so coverage can only come from the rows given.
        _archive(monkeypatch)

    def test_a_compound_archive_row_covers_neither_hazard_now(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Both of its hazards moved to live catalogues, so the archive drops it.

        This once asserted the opposite, and for a real reason: a compound row
        labelled only `tsunami` had hidden 170,791 earthquake deaths, and the
        `hazard_types` array was added so one row could register under both
        names. Earthquakes now come from USGS and tsunamis from NOAA/NCEI, so a
        district-wide row for either is excluded — and crediting the archive for
        hazards it is no longer read for would be the same lie in reverse.
        """
        self._offline(monkeypatch)
        palu = DisasterEvent(
            id="desinventar-palu",
            type="earthquake and tsunami",
            hazard_types=["earthquake", "tsunami"],
            title="Earthquake and tsunami — Kota Palu",
            source="BNPB DIBI (DesInventar)",
            scope="regional",
            distance_meters=1_000.0,
        )

        history, _ = asyncio.run(
            disasters_service.get_disaster_history(
                -0.9, 119.9, local_events=[palu], skip_database=True
            )
        )

        assert history.events == []
        assert "earthquake" not in history.covered_types
        assert "tsunami" not in history.covered_types

    def test_a_single_hazard_event_covers_only_itself(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._offline(monkeypatch)
        flood = DisasterEvent(
            id="desinventar-flood",
            type="flood",
            title="Flood — Kota Tangerang",
            source="BNPB DIBI (DesInventar)",
            scope="regional",
            distance_meters=2_000.0,
        )

        history, _ = asyncio.run(
            disasters_service.get_disaster_history(
                -6.3, 106.7, local_events=[flood], skip_database=True
            )
        )

        assert history.covered_types == ["flood"]
        # The absence has to stay meaningful: nothing invents tsunami coverage.
        assert "tsunami" not in history.covered_types


class TestCatalogueCoverage:
    """Coverage follows the catalogue searched, not the rows it returned.

    A pin in Serpong has no eruption on record, but the archive holding 245
    eruption records was still queried for it. Deriving coverage from the answer
    made the section announce "not searched here: volcanic eruption, wildfire" —
    turning a genuine all-clear into a false gap, and telling the reader to go
    load an importer that had already been run.
    """

    @staticmethod
    def _offline(monkeypatch: pytest.MonkeyPatch, **overrides: object) -> None:
        from api.core.config import Settings

        pinned: dict[str, object] = {
            "enable_external_apis": False,
            "disaster_require_measured_location": False,
        }
        pinned.update(overrides)
        settings = Settings(**pinned)
        monkeypatch.setattr(disasters_service, "get_settings", lambda: settings)

    def test_the_archive_covers_hazards_it_returned_nothing_for(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._offline(monkeypatch)
        _archive(monkeypatch, *disasters_service.IMPORTABLE_TYPES)
        flood = DisasterEvent(
            id="desinventar-1",
            type="flood",
            title="Flood — Tangerang",
            source="BNPB DIBI (DesInventar)",
            scope="regional",
            distance_meters=0.0,
        )

        history, _ = asyncio.run(
            disasters_service.get_disaster_history(
                -6.306, 106.686, local_events=[flood], skip_database=True
            )
        )

        assert "volcanic eruption" in history.covered_types
        assert "wildfire" in history.covered_types
        # Tsunami is NOAA/NCEI's now, so the archive no longer claims it — with
        # external APIs off in this test, nothing does.
        assert "tsunami" not in history.covered_types
        # Tsunami is the one gap left, because its source is a live API and
        # this test has the network taken away.
        assert history.note is not None
        assert "tsunami" in history.note

    def test_measured_only_claims_no_archive_coverage(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The flag discards every archive row, so its coverage goes with them.

        The search did run — but none of its answers survive to be reported on,
        and claiming otherwise would say floods were covered while every flood
        record had just been dropped.
        """
        self._offline(monkeypatch, disaster_require_measured_location=True)
        _archive(monkeypatch, *disasters_service.IMPORTABLE_TYPES)
        flood = DisasterEvent(
            id="desinventar-1",
            type="flood",
            title="Flood — Tangerang",
            source="BNPB DIBI (DesInventar)",
            scope="regional",
            distance_meters=0.0,
        )

        history, _ = asyncio.run(
            disasters_service.get_disaster_history(
                -6.306, 106.686, local_events=[flood], skip_database=True
            )
        )

        assert "flood" not in history.covered_types


class TestMissingHazardNote:
    """An unsearched hazard has to be named, especially the one that isn't there.

    No live source carries tsunami. USGS is a seismic network publishing
    earthquakes; GDACS has no tsunami event type at all — it answers HTTP 204
    for `eventlist=TS` and only ever emits EQ, FL, TC, WF, DR, VO. So until the
    DIBI archive is imported, tsunami history simply does not exist in a report.

    The note used to be a fixed sentence about "floods, landslides and
    windstorms", which on a beach in Banda Aceh omitted the single hazard a
    reader standing there most needs to know was unsearched.
    """

    def test_tsunami_is_importable_but_not_live(self) -> None:
        assert "tsunami" in disasters_service.IMPORTABLE_TYPES
        assert "tsunami" not in disasters_service.USGS_TYPES
        assert "tsunami" not in gdacs.EVENT_TYPES.values()

    def test_the_note_names_the_missing_hazards(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from api.core.config import Settings

        # Pinned, not inherited: `Settings()` reads the developer's `.env`,
        # so an unpinned flag would make these pass or fail by machine.
        settings = Settings(
            enable_external_apis=False,
            disaster_require_measured_location=False,
        )
        monkeypatch.setattr(disasters_service, "get_settings", lambda: settings)
        _archive(monkeypatch)
        # More than earthquakes, so this isn't the "only USGS answered" case,
        # but well short of the archive — a partial import, or the live feeds
        # on their own, which is where every report starts.
        stored = [
            DisasterEvent(id="db-1", type="earthquake", title="a", source="db"),
            DisasterEvent(id="db-2", type="flood", title="b", source="db"),
        ]

        history, _ = asyncio.run(
            disasters_service.get_disaster_history(
                5.57, 95.32, local_events=stored, skip_database=True
            )
        )

        assert history.note is not None
        assert "tsunami" in history.note
        # And it must not claim a hazard is missing when it was searched.
        assert "earthquake" not in history.note

    def test_importable_types_match_the_importer(self) -> None:
        """The two lists drift apart silently otherwise."""
        import importlib.util
        from pathlib import Path

        spec = importlib.util.spec_from_file_location(
            "import_desinventar",
            Path(__file__).resolve().parent.parent / "scripts" / "import_desinventar.py",
        )
        assert spec and spec.loader
        importer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(importer)

        atomic: set[str] = set()
        for label in importer.EVENT_TYPES.values():
            atomic.update(importer.HAZARD_TYPES.get(label, [label]))

        assert atomic == set(disasters_service.IMPORTABLE_TYPES)
