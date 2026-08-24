"""Flood risk.

Three sources, in descending order of authority:

1. A mapped hazard polygon in PostGIS (`flood_zones`) — if you've imported local
   government data, it wins.
2. BNPB **InaRISK** `layer_bahaya_banjir` — the official Indonesian national
   flood hazard model, sampled at the point.
3. A deliberately simple heuristic — how low the ground is, how close the
   nearest water is — used only when neither of the above answers.

The `basis` and `confidence` fields say which of the three decided the result,
so a modelled guess is never mistaken for an official one.
"""

from __future__ import annotations

from api.db import repository
from api.schemas.common import DataSource, RiskLevel
from api.schemas.location import FloodInfo, HazardReading, TerrainInfo, WaterFeature
from api.services import waterways


def _elevation_points(elevation: float | None) -> tuple[int, str | None]:
    if elevation is None:
        return 0, None
    if elevation < 5:
        return 3, "the ground is barely above sea level"
    if elevation < 15:
        return 2, "the ground sits low"
    if elevation < 40:
        return 1, "the ground is moderately low"
    if elevation > 150:
        return -1, "the ground is well elevated"
    return 0, None


def _water_points(water: WaterFeature | None) -> tuple[int, str | None]:
    if water is None:
        return 0, None

    label = water.name or f"a {water.kind}"
    distance = water.distance_meters

    if distance < 100:
        return 3, f"{label} runs within {round(distance)} m"
    if distance < 300:
        return 2, f"{label} is about {round(distance)} m away"
    if distance < 1000:
        return 1, f"{label} is roughly {round(distance / 100) * 100} m away"
    return 0, None


def _level_from_score(score: int) -> RiskLevel:
    if score >= 4:
        return "high"
    if score >= 2:
        return "medium"
    return "low"


def _join(parts: list[str]) -> str:
    if len(parts) == 1:
        return parts[0]
    return f"{', '.join(parts[:-1])} and {parts[-1]}"


def _compose_reason(level: RiskLevel, raising: list[str], easing: list[str]) -> str:
    """Explain the level in plain language, keeping risks and comforts apart."""
    if not raising and not easing:
        return (
            "Nothing in our data points to a flood problem here, but we also have "
            "little to go on. Treat this as 'unverified', not 'safe'."
        )

    if not raising:
        return f"Nothing here raises a flag. {_join(easing)}."

    match level:
        case "high":
            sentence = (
                f"Flagged because {_join(raising)}. Ask locally how this spot "
                "behaves in the wet season."
            )
        case "medium":
            sentence = f"Worth a closer look: {_join(raising)}."
        case _:
            sentence = f"Only minor signals here: {_join(raising)}."

    if easing:
        sentence += f" On the other hand, {_join(easing)}."
    return sentence


def _inarisk_reason(hazard: HazardReading, water: WaterFeature | None) -> str:
    """Wording for a risk level that came from BNPB's own model.

    The claim has to match where the value was actually measured: saying "this
    point" about a reading taken 1 km away would misstate the evidence.
    """
    index = hazard.index or 0.0
    distance = hazard.within_meters or 0.0
    strength = {"high": "high", "medium": "moderate", "low": "low"}[hazard.level]

    if distance >= 1:
        lead = (
            f"BNPB's InaRISK model maps a {strength} flood-hazard area "
            f"{round(distance)} m from this point (index {index:.2f} of 1.00). "
            "The plot itself is outside the mapped zone."
        )
    else:
        lead = (
            f"BNPB's InaRISK model puts this point in a {strength} flood-hazard "
            f"area (index {index:.2f} of 1.00)."
        )

    if water is not None:
        label = water.name or f"a {water.kind}"
        lead += f" {label} is {round(water.distance_meters)} m away."

    return lead


def _inarisk_reading(
    hazard: HazardReading | None,
) -> tuple[float | None, RiskLevel | None]:
    """The InaRISK flood reading, kept whichever source decides the level.

    Every branch below reports this, not just the one that acts on it. A mapped
    zone calling a plot high-risk while BNPB's model reads 0.20 is the strongest
    signal this section has; returning only the winner threw it away.
    """
    if hazard is None or hazard.status != "ok" or hazard.index is None:
        return None, None
    return hazard.index, hazard.level  # type: ignore[return-value]


async def assess_flood_risk(
    latitude: float,
    longitude: float,
    terrain: TerrainInfo,
    hazard: HazardReading | None = None,
    *,
    local_zone: tuple[str | None, str] | None = None,
    local_water: WaterFeature | None = None,
    skip_local_queries: bool = False,
) -> tuple[FloodInfo, list[DataSource]]:
    """Decide a flood risk level, preferring mapped data over any model.

    `local_zone`/`local_water` carry values a caller already read from PostGIS.
    `skip_local_queries` says those lookups have been done and came back empty,
    so this shouldn't repeat them.
    """
    sources: list[DataSource] = []
    inarisk_index, inarisk_level = _inarisk_reading(hazard)

    if local_water is not None:
        water = local_water
        sources.append(DataSource(field="waterways", provider="postgis", quality="database"))
    else:
        water, water_source = await waterways.nearest_water(
            latitude, longitude, skip_database=skip_local_queries
        )
        sources.append(water_source)

    # 1. Locally imported hazard polygons are the most specific thing we have.
    zone = local_zone
    if zone is None and not skip_local_queries:
        zone = await repository.flood_zone_at(latitude, longitude)
    if zone is not None:
        zone_name, risk_level = zone
        sources.append(DataSource(field="flood", provider="postgis", quality="database"))
        return (
            FloodInfo(
                risk=risk_level,  # type: ignore[arg-type]
                reason=(
                    f"This point falls inside a mapped {risk_level}-risk flood zone"
                    + (f" ({zone_name})." if zone_name else ".")
                ),
                nearest_river=water,
                zone_name=zone_name,
                confidence="high",
                hazard_index=inarisk_index,
                hazard_level=inarisk_level,
                basis="postgis",
            ),
            sources,
        )

    # 2. BNPB's national model. Authoritative wherever it has coverage.
    if hazard is not None and hazard.status == "ok" and hazard.index is not None:
        sources.append(
            DataSource(
                field="flood",
                provider="inarisk",
                quality="live",
                note="BNPB InaRISK national flood hazard index.",
            )
        )
        return (
            FloodInfo(
                risk=hazard.level,
                reason=_inarisk_reason(hazard, water),
                nearest_river=water,
                zone_name=None,
                confidence="high",
                hazard_index=inarisk_index,
                hazard_level=inarisk_level,
                basis="inarisk",
            ),
            sources,
        )

    # 3. Fall back to the local heuristic, and label it as such.
    elevation_score, elevation_signal = _elevation_points(terrain.elevation)
    water_score, water_signal = _water_points(water)

    raising = [
        signal
        for score, signal in ((elevation_score, elevation_signal), (water_score, water_signal))
        if signal and score > 0
    ]
    easing = [
        signal
        for score, signal in ((elevation_score, elevation_signal), (water_score, water_signal))
        if signal and score <= 0
    ]

    if terrain.elevation is None and water is None:
        sources.append(
            DataSource(
                field="flood",
                provider="heuristic",
                quality="unavailable",
                note="No flood zone, hazard index, elevation or waterway data was available.",
            )
        )
        return (
            FloodInfo(
                risk="unknown",
                reason=(
                    "No flood model answered and we have no elevation or waterway "
                    "data here, so there's no honest flood read to give you."
                ),
                nearest_river=None,
                zone_name=None,
                confidence="none",
                basis="none",
            ),
            sources,
        )

    level = _level_from_score(elevation_score + water_score)
    # An estimate built on one signal is weaker than one built on two.
    confidence = "medium" if terrain.elevation is not None and water is not None else "low"

    note = "Derived from elevation and distance to water."
    if hazard is not None and hazard.status == "unavailable":
        note += " BNPB InaRISK was unreachable."
    elif hazard is not None and hazard.status == "no_data":
        note += " This point is outside InaRISK's modelled flood area."

    sources.append(DataSource(field="flood", provider="heuristic", quality="estimate", note=note))

    return (
        FloodInfo(
            risk=level,
            reason=_compose_reason(level, raising, easing),
            nearest_river=water,
            zone_name=None,
            confidence=confidence,
            hazard_index=inarisk_index,
            hazard_level=inarisk_level,
            basis="heuristic",
        ),
        sources,
    )
