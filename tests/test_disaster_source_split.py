"""Each hazard has exactly one catalogue behind it.

Earthquakes come from USGS, tsunamis from NOAA/NCEI, everything else from the
imported BNPB archive. The archive holds earthquake and tsunami records too, so
without this split the same event arrives twice — once at a measured epicentre
or runup, once as a district with no position inside it.

The split has a large, deliberate cost. DIBI is the only source here that counts
casualties, so no recorded earthquake or tsunami death is shown any more: 3,624
at Palu, 128,728 in Aceh, 170,791 in total. USGS publishes PAGER estimates and
NCEI counts per event rather than per observation, so neither replaces them.
These tests pin the split, and name the cost so it cannot be reintroduced by
accident and cannot be forgotten either.
"""

from __future__ import annotations

import asyncio

import pytest

from api.schemas.location import DisasterEvent, DisasterImpact
from api.services import disasters as disasters_service


def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin settings and take the network away, leaving stored rows alone."""
    from api.core.config import Settings

    settings = Settings(
        enable_external_apis=False,
        disaster_require_measured_location=False,
    )
    monkeypatch.setattr(disasters_service, "get_settings", lambda: settings)

    async def _no_archive() -> frozenset[str]:
        return frozenset()

    monkeypatch.setattr(disasters_service, "_archived_hazards", _no_archive)


def archived(**overrides) -> DisasterEvent:
    """A district-wide row of the kind the importer writes."""
    row = {
        "id": "desinventar-1",
        "type": "flood",
        "hazard_types": ["flood"],
        "title": "Kota Palu",
        "source": "BNPB DIBI (DesInventar)",
        "occurred_at": "2018-09-28T00:00:00+00:00",
        "scope": "regional",
        "distance_meters": 0.0,
        "impact": DisasterImpact(deaths=3624),
    }
    row.update(overrides)
    return DisasterEvent(**row)


def history(monkeypatch: pytest.MonkeyPatch, stored: list[DisasterEvent]):
    return asyncio.run(
        disasters_service.get_disaster_history(
            -0.8990, 119.8707, local_events=stored, skip_database=True
        )
    )[0]


class TestArchiveIsExcluded:
    @pytest.mark.parametrize(
        ("hazards", "label"),
        [
            pytest.param(["earthquake"], "earthquake", id="earthquake"),
            pytest.param(["tsunami"], "tsunami", id="tsunami"),
            pytest.param(
                ["earthquake", "tsunami"], "earthquake and tsunami", id="compound"
            ),
        ],
    )
    def test_the_archive_supplies_neither_hazard(
        self, monkeypatch: pytest.MonkeyPatch, hazards: list[str], label: str
    ) -> None:
        """Including the compound rows, which are both at once.

        The 27 `earthquake and tsunami` rows carry Palu's and Aceh's tolls, and
        they go too: a row that is partly an earthquake record is still an
        earthquake record.
        """
        offline(monkeypatch)

        result = history(monkeypatch, [archived(type=label, hazard_types=hazards)])

        assert result.events == []

    def test_every_other_hazard_keeps_its_tolls(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The split is about two hazards, not about the archive as a whole."""
        offline(monkeypatch)

        result = history(monkeypatch, [archived()])

        assert len(result.events) == 1
        assert result.events[0].impact.deaths == 3624

    def test_coverage_does_not_credit_the_archive(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A hazard read from a live API must not be claimed by the database.

        With the network off, nothing covers earthquake or tsunami, and saying
        otherwise would tell a reader they were searched when they were not.
        """
        offline(monkeypatch)

        async def _full_archive() -> frozenset[str]:
            return frozenset(disasters_service.IMPORTABLE_TYPES)

        monkeypatch.setattr(disasters_service, "_archived_hazards", _full_archive)

        result = history(monkeypatch, [archived()])

        assert "earthquake" not in result.covered_types
        assert "tsunami" not in result.covered_types
        assert "flood" in result.covered_types


class TestNoLossLookup:
    def test_the_archive_is_not_queried_for_earthquake_losses(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`quake_losses_near` would put back exactly what the split removes.

        It runs after the display filter, so leaving it wired in reintroduced
        every district row the filter had just dropped.
        """
        offline(monkeypatch)

        async def _fail(*args, **kwargs):  # pragma: no cover - must not run
            raise AssertionError("the archive was queried for earthquake losses")

        monkeypatch.setattr(
            disasters_service.repository, "quake_losses_near", _fail
        )

        usgs = DisasterEvent(
            id="usgs-1",
            type="earthquake",
            hazard_types=["earthquake"],
            title="16 km SSE of Palu, Indonesia",
            source="USGS",
            occurred_at="2018-09-28T10:25:04+00:00",
            scope="point",
            distance_meters=17_000.0,
            distance_basis="measured",
            magnitude=5.8,
        )

        result = history(monkeypatch, [usgs])

        assert [event.source for event in result.events] == ["USGS"]


class TestEarthquakeReach:
    """Epicentre distance is the wrong ruler for an earthquake.

    The M7.5 that destroyed Palu on 28 September 2018 has its epicentre 71.6 km
    from the city, 20 km deep, and shook it at MMI 8.4 with 40 felt reports.
    Asked only for 25 km, USGS never returned it — so the section listed an M5.8
    aftershock and left out the earthquake that levelled the place. Nothing
    filtered it; it was never requested.
    """

    def test_usgs_is_asked_over_its_own_radius(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from api.core.config import Settings

        settings = Settings(
            disaster_radius_meters=25_000,
            earthquake_radius_meters=200_000,
            disaster_require_measured_location=False,
        )
        monkeypatch.setattr(disasters_service, "get_settings", lambda: settings)

        asked: dict[str, float] = {}

        async def _capture(latitude, longitude, radius_meters, years):
            asked["radius"] = radius_meters
            return []

        monkeypatch.setattr(disasters_service, "_fetch_earthquakes", _capture)

        async def _none(*args, **kwargs):
            return []

        monkeypatch.setattr(disasters_service, "_fetch_custom_feed", _none)
        monkeypatch.setattr(disasters_service.ncei_tsunami, "fetch_runups", _none)

        async def _no_archive() -> frozenset[str]:
            return frozenset()

        monkeypatch.setattr(disasters_service, "_archived_hazards", _no_archive)
        disasters_service._cache._store.clear()

        result = asyncio.run(
            disasters_service.get_disaster_history(
                -0.8990, 119.8707, local_events=[], skip_database=True
            )
        )[0]

        # The archive's radius must not be what USGS is asked for.
        assert asked["radius"] == 200_000
        # And the caption has to say so, or a row reading "72 km" contradicts it.
        assert result.earthquake_radius_meters == 200_000

    def test_the_wider_reach_is_not_announced_when_it_matches(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Nothing to explain when both radii agree — so say nothing."""
        from api.core.config import Settings

        settings = Settings(
            disaster_radius_meters=25_000,
            earthquake_radius_meters=25_000,
            disaster_require_measured_location=False,
        )
        monkeypatch.setattr(disasters_service, "get_settings", lambda: settings)

        async def _none(*args, **kwargs):
            return []

        monkeypatch.setattr(disasters_service, "_fetch_earthquakes", _none)
        monkeypatch.setattr(disasters_service, "_fetch_custom_feed", _none)
        monkeypatch.setattr(disasters_service.ncei_tsunami, "fetch_runups", _none)

        async def _no_archive() -> frozenset[str]:
            return frozenset()

        monkeypatch.setattr(disasters_service, "_archived_hazards", _no_archive)
        disasters_service._cache._store.clear()

        result = asyncio.run(
            disasters_service.get_disaster_history(
                -0.8990, 119.8707, local_events=[], skip_database=True
            )
        )[0]

        assert result.earthquake_radius_meters is None
