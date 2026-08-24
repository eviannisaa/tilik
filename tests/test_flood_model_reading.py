"""The InaRISK flood reading survives whichever source decides the level.

Dropping it was hiding the case worth showing: a locally mapped zone and BNPB's
national model disagreeing. These pin that the index is reported by the branch
that ignores it, not only by the one that acts on it.

`nearest_water` is patched throughout — this is about which reading comes back,
and letting it reach Overpass makes the suite slow and non-deterministic.
"""

from __future__ import annotations

import asyncio

import pytest

from api.schemas.common import DataSource
from api.schemas.location import HazardReading, TerrainInfo, WaterFeature
from api.services import flood as flood_service
from api.services.flood import assess_flood_risk


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _nearest_water(*_args, **_kwargs):
        return None, DataSource(field="waterways", provider="overpass", quality="unavailable")

    monkeypatch.setattr(flood_service.waterways, "nearest_water", _nearest_water)


def _terrain(elevation: float | None) -> TerrainInfo:
    return TerrainInfo(
        elevation=elevation,
        unit="meters",
        terrain="lowland",
        description="",
        confidence="high",
    )


def _reading(index: float | None, level: str, status: str = "ok") -> HazardReading:
    return HazardReading(
        key="flood",
        label="Flood",
        index=index,
        level=level,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        source="inarisk",
        resolution_meters=None,
        within_meters=0,
        description="",
    )


def _assess(*, elevation: float | None = 40.0, hazard=None, local_zone=None, local_water=None):
    return asyncio.run(
        assess_flood_risk(
            -6.1,
            106.8,
            _terrain(elevation),
            hazard,
            local_zone=local_zone,
            local_water=local_water,
            skip_local_queries=True,
        )
    )


def test_mapped_zone_wins_but_still_reports_the_model() -> None:
    """The case this change exists for: the zone decides, the index still ships."""
    flood, _ = _assess(hazard=_reading(0.20, "low"), local_zone=("Kelurahan Pluit", "high"))

    assert flood.basis == "postgis"
    assert flood.risk == "high"
    # Without these two, nothing downstream could say the model disagrees.
    assert flood.hazard_index == 0.20
    assert flood.hazard_level == "low"


def test_the_model_deciding_reports_itself() -> None:
    flood, _ = _assess(hazard=_reading(0.78, "high"))

    assert flood.basis == "inarisk"
    assert flood.risk == "high"
    assert flood.hazard_index == 0.78
    assert flood.hazard_level == "high"


def test_an_answering_model_outranks_the_heuristic() -> None:
    """Ground barely above sea level would score `high` on its own, but a layer
    that answered is authoritative — so the heuristic never runs, and `basis`
    says which one spoke."""
    flood, _ = _assess(hazard=_reading(0.10, "low"), elevation=2.0)

    assert flood.basis == "inarisk"
    assert flood.risk == "low"


def test_heuristic_runs_only_when_the_model_is_silent() -> None:
    """`no_data` carries no index, so there is nothing to report alongside it."""
    flood, _ = _assess(hazard=_reading(None, "unknown", status="no_data"), elevation=3.0)

    assert flood.basis == "heuristic"
    assert flood.risk in {"medium", "high"}
    assert flood.hazard_index is None
    assert flood.hazard_level is None


def test_no_reading_at_all_leaves_both_empty() -> None:
    flood, _ = _assess(hazard=None, elevation=None)

    assert flood.hazard_index is None
    assert flood.hazard_level is None


def test_a_zone_with_no_model_reading_reports_no_index() -> None:
    flood, _ = _assess(hazard=None, local_zone=("Kelurahan Pluit", "high"))

    assert flood.basis == "postgis"
    assert flood.hazard_index is None
    assert flood.hazard_level is None
