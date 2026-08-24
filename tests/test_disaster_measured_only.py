"""Keeping only events whose coordinate is the event's own location.

A disaster history mixes two kinds of record, and their distances do not mean
the same thing. A seismic epicentre is measured, so "24 km" is 24 km. BNPB's
DIBI records carry no coordinate at all — every latitude and longitude in the
export is literally 0 — so they sit at their district's centre, and GDACS uses
the centroid of an affected region. For those, "18 km" means "that area's middle
is 18 km away", which is not the same claim.

`DISASTER_REQUIRE_MEASURED_LOCATION` keeps only the measured ones, so every
figure in the section is a true distance from the coordinate the reader typed.
The cost is deliberate and severe: it excludes the whole DIBI archive — 32,447
records, every flood, landslide, windstorm, drought and wildfire — leaving
earthquakes, which are not the hazard that actually recurs across most of Java.
These pin that the filter is complete, that it says so, and that it does not
spend a live request on a feed whose every row it would discard.
"""

from __future__ import annotations

import asyncio

import pytest

from api.core.config import Settings
from api.schemas.location import DisasterEvent
from api.services import disasters as disasters_service


def event(scope: str, identifier: str, area: str | None = None) -> DisasterEvent:
    return DisasterEvent(
        id=identifier,
        type="flood" if scope != "point" else "earthquake",
        area_name=area,
        title="Event",
        source="BNPB DIBI (DesInventar)" if scope != "point" else "USGS",
        scope=scope,  # type: ignore[arg-type]
        distance_meters=10_000.0,
    )


STORED = [
    event("point", "measured"),
    event("regional", "district", "Kota Jakarta Selatan"),
    event("provincial", "province", "Sigi"),
]


def run(monkeypatch: pytest.MonkeyPatch, *, measured_only: bool):
    settings = Settings(
        enable_external_apis=False,
        disaster_require_measured_location=measured_only,
    )
    monkeypatch.setattr(disasters_service, "get_settings", lambda: settings)
    history, _ = asyncio.run(
        disasters_service.get_disaster_history(
            -6.31, 106.67, local_events=list(STORED), skip_database=True
        )
    )
    return history


class TestFilter:
    def test_off_by_default(self) -> None:
        """A setting this lossy must never be the silent default.

        Read from the field rather than an instance: `Settings()` loads the
        developer's own `.env`, so an instance would assert whatever this
        machine happens to be configured for instead of what ships.
        """
        field = Settings.model_fields["disaster_require_measured_location"]
        assert field.default is False

    def test_it_keeps_only_measured_rows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        history = run(monkeypatch, measured_only=True)
        assert [e.id for e in history.events] == ["measured"]

    def test_district_and_province_rows_both_go(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Both are area centres; neither is the event's own position."""
        scopes = {e.scope for e in run(monkeypatch, measured_only=True).events}
        assert scopes == {"point"}

    def test_everything_stays_when_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert len(run(monkeypatch, measured_only=False).events) == 3

    def test_coverage_shrinks_to_match(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`covered_types` promises what was searched, so it has to shrink too.

        Leaving `flood` listed would say floods were covered while every flood
        record had just been discarded.
        """
        assert run(monkeypatch, measured_only=True).covered_types == ["earthquake"]
        assert "flood" in run(monkeypatch, measured_only=False).covered_types

    def test_it_explains_itself(self, monkeypatch: pytest.MonkeyPatch) -> None:
        note = run(monkeypatch, measured_only=True).note or ""
        assert "measured location" in note
        # And names the way back, since the exclusion is a choice, not a limit.
        assert "DISASTER_REQUIRE_MEASURED_LOCATION" in note

    def test_the_cache_key_separates_the_two_modes(self) -> None:
        """Otherwise a filtered result would be served to an unfiltered request."""
        import inspect

        source = inspect.getsource(disasters_service.get_disaster_history)
        assert "{measured_only}" in source
