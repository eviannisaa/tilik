"""The overall "should I look closer at this?" summary.

This is a transparent rule set, not a model. Every point that moves the level
also produces a factor the UI shows, so a user can see exactly why the report
landed where it did — and the confidence field says how thin the evidence is.
"""

from __future__ import annotations

from api.schemas.common import AssessmentLevel, ConfidenceLevel
from api.schemas.location import (
    AirQuality,
    DisasterHistory,
    FloodInfo,
    HazardIndex,
    HazardReading,
    NearbyPlaces,
    TerrainInfo,
)
from api.schemas.report import Assessment, AssessmentFactor
from api.services.inarisk import AT_PLOT_METERS

#: Events closer than this are treated as "right here" rather than "in the region".
NEARBY_EVENT_METERS = 15_000
SIGNIFICANT_MAGNITUDE = 6.0
#: Hazards other than flood that InaRISK models; flood has its own factor.
#: Flood has its own factor via the flood section, so it's excluded here to
#: avoid double-weighting the same reading. Drought and extreme weather are
#: modelled almost everywhere in Indonesia, so they'd flag every location and
#: are reported without contributing to the score.
SECONDARY_HAZARDS = (
    "flashFlood",
    "landslide",
    "earthquake",
    "liquefaction",
    "tsunami",
    "coastalErosion",
    "volcanic",
    "wildfire",
)

#: One line per verdict, and each says two things: what the sources show, and
#: what to do about it.
#:
#: The register is deliberate. These lines carried "green light", "clean bill of
#: health", "deal-breakers" and "get someone on the ground" — idiom stacked on
#: idiom, in a report a buyer may show to a notary, a lender or a family. Idiom
#: also travels badly: a reader working in English as a second language has to
#: decode "clean bill of health" before reaching the point, and the point is the
#: only thing that matters. Each line now states the finding plainly and names
#: the next step.
HEADLINES: dict[AssessmentLevel, str] = {
    "low": (
        "The sources reviewed show no elevated hazard at this point. That is "
        "grounds to continue your enquiries, not confirmation that the parcel is "
        "sound."
    ),
    "moderate": (
        "Some findings here warrant clarification before you commit. None of them "
        "is disqualifying on its own."
    ),
    "higher": (
        "The findings here warrant inspection before you proceed. Arrange a site "
        "visit, and consider a professional survey of the parcel."
    ),
    "unknown": (
        "Not enough data was available to assess this point. Please try again "
        "shortly, or select a nearby location."
    ),
}


def _flood_factor(flood: FloodInfo) -> tuple[int, AssessmentFactor | None]:
    match flood.risk:
        case "high":
            return 3, AssessmentFactor(
                label="Flood risk", detail=flood.reason, impact="negative"
            )
        case "medium":
            return 2, AssessmentFactor(
                label="Some flood exposure", detail=flood.reason, impact="negative"
            )
        case "low":
            return 0, AssessmentFactor(
                label="Flood risk looks low", detail=flood.reason, impact="positive"
            )
        case _:
            return 0, AssessmentFactor(
                label="Flood risk unknown",
                detail="We had no flood, elevation or waterway data for this point.",
                impact="neutral",
            )


def _terrain_factor(terrain: TerrainInfo) -> tuple[int, AssessmentFactor | None]:
    match terrain.terrain:
        case "coastal":
            return 1, AssessmentFactor(
                label="Coastal ground",
                detail="Barely above sea level, so tides and surge matter here.",
                impact="negative",
            )
        case "mountainous":
            return 1, AssessmentFactor(
                label="Steep ground",
                detail="Mountainous terrain brings slope stability and access questions.",
                impact="negative",
            )
        case "hilly" | "highland":
            return 0, AssessmentFactor(
                label="Well-drained ground",
                detail=(
                    f"Sitting around {round(terrain.elevation or 0)} m, water runs off "
                    "rather than pools."
                ),
                impact="positive",
            )
        case "unknown":
            return 0, None
        case _:
            return 0, None


def _distance_of(event) -> float:
    """`distance_meters`, with a missing value sorting last rather than first.

    Written out because `event.distance_meters or float("inf")` maps 0.0 to
    infinity — and 0.0 is exactly what an archive row carries when the checked
    coordinate falls inside its district, which is the commonest case here.
    """
    return float("inf") if event.distance_meters is None else event.distance_meters


def _loss_of(event) -> int:
    """The heaviest human cost the record carries, as one comparable number.

    Deaths and missing are counted as they are; displacement is divided so that
    a few thousand evacuated does not outrank a death toll. Only the archive
    records any of this — USGS publishes estimates and NOAA/NCEI counts per
    event rather than per observation — so this is the only place casualty
    figures can come from.
    """
    if event.impact is None:
        return 0
    return max(
        event.impact.deaths or 0,
        event.impact.missing or 0,
        (event.impact.displaced or 0) // 100,
    )


def _loss_phrase(event) -> str:
    """The figures themselves, in the order a reader cares about them."""
    impact = event.impact
    parts: list[str] = []
    if impact is not None:
        if impact.deaths:
            parts.append(f"{impact.deaths:,} killed")
        if impact.missing:
            parts.append(f"{impact.missing:,} missing")
        if impact.displaced:
            parts.append(f"{impact.displaced:,} displaced")
    return ", ".join(parts) if parts else "Casualties recorded"


def _when(event) -> str:
    """The year, which is all a one-line factor has room for."""
    return event.occurred_at[:4] if event.occurred_at else "an unrecorded year"


def _distance_phrase(event) -> str:
    """How far away, phrased by what the figure actually measures.

    The same three cases the disaster list distinguishes: a measured position, a
    district holding the coordinate, and a district whose nearest edge is this
    far off — where the figure is a lower bound and not a measurement.
    """
    if event.distance_basis == "measured":
        metres = _distance_of(event)
        if metres == float("inf"):
            return "at an unrecorded distance"
        return f"{metres / 1000:.0f} km from your coordinate"
    if event.distance_basis == "area_edge" and not event.distance_meters:
        return "in this district"
    if event.distance_basis == "area_edge":
        return f"at least {_distance_of(event) / 1000:.1f} km away"
    return f"about {_distance_of(event) / 1000:.0f} km from the area's centre"


def _common_hazards(disasters: DisasterHistory, limit: int = 3) -> str:
    """The hazards that recur, not every hazard present.

    Listing all of them alphabetically produced "coastal erosion, drought,
    earthquake, extreme weather, fire, flood, landslide, tsunami" — a tag dump
    that buried whichever one actually happens here.
    """
    counts: dict[str, int] = {}
    for event in disasters.events:
        for hazard in event.hazard_types:
            counts[hazard] = counts.get(hazard, 0) + 1
    ranked = sorted(counts, key=lambda hazard: (-counts[hazard], hazard))[:limit]
    return ", ".join(ranked) if ranked else "no particular hazard"


def _tsunami_factor(disasters: DisasterHistory) -> tuple[int, AssessmentFactor | None]:
    """A tsunami that reached here, with the height it reached.

    Kept separate from `_disaster_factor` rather than competing with it. Ordering
    them in one slot meant whichever came first won, and both orders were wrong:
    a 2013 flood with one death outranked the 50.9 m wave that reached Banda
    Aceh, while putting the tsunami first would have buried a hundred deaths
    behind a half-metre swell. They are different facts about a plot and both
    belong on the list.

    NOAA/NCEI records height per observation, which makes it the one tsunami
    figure that is genuinely local; the casualty totals in the same database are
    per event and are deliberately not carried.
    """
    wetted = max(
        (event for event in disasters.events if event.water_height_m),
        key=lambda event: event.water_height_m or 0,
        default=None,
    )
    if wetted is None:
        return 0, None

    height = wetted.water_height_m or 0
    return (
        2 if height >= 1 else 1,
        AssessmentFactor(
            label="Tsunami reached here",
            detail=(
                f"Water reached {height:.1f} m at {wetted.title} in "
                f"{_when(wetted)}, {_distance_phrase(wetted)}."
            ),
            impact="negative",
        ),
    )


def _disaster_factor(disasters: DisasterHistory) -> tuple[int, AssessmentFactor | None]:
    if not disasters.events:
        if disasters.confidence == "none":
            return 0, None

        radius_km = disasters.radius_meters // 1000
        # Crediting "nothing recorded" as good news is only fair if more than one
        # kind of disaster was actually searched for.
        if set(disasters.covered_types) <= {"earthquake"}:
            return 0, AssessmentFactor(
                label="Only quakes were checked",
                detail=(
                    f"No earthquakes logged within {radius_km} km, but flood, "
                    "landslide and eruption records weren't searched, so this "
                    "isn't an all-clear."
                ),
                impact="neutral",
            )

        return 0, AssessmentFactor(
            label="No recorded events",
            detail=f"Nothing logged within {radius_km} km in the sources we check.",
            impact="positive",
        )

    radius_km = disasters.radius_meters // 1000

    # What people actually lost comes first. The archive is the only source here
    # that counts casualties, and a place with 100 recorded deaths and a place
    # with none used to produce the same sentence — a comma-separated list of
    # every hazard type present, which said nothing about severity at all.
    worst_loss = max(
        (event for event in disasters.events if _loss_of(event)),
        key=_loss_of,
        default=None,
    )
    if worst_loss is not None:
        impact = worst_loss.impact
        # Named for what the record holds, in the order that matters. A death
        # takes the label whenever there is one, even where displacement is the
        # larger figure — but "Recorded loss of life" over a row of 13,280
        # displaced and nobody killed claims a death toll the archive never
        # reported.
        if impact and impact.deaths:
            label = "Recorded loss of life"
        elif impact and impact.missing:
            label = "People unaccounted for"
        else:
            label = "People displaced here"
        return 3, AssessmentFactor(
            label=label,
            detail=(
                f"{_loss_phrase(worst_loss)} at {worst_loss.title}, "
                f"{_when(worst_loss)}. {len(disasters.events)} events on record "
                f"within {radius_km} km."
            ),
            impact="negative",
        )

    # Only a measured epicentre can support a "right here" claim: an archive row
    # carries no position inside its district, so its distance is the district's,
    # not the event's.
    strong = [
        event
        for event in disasters.events
        if event.distance_basis == "measured"
        and (event.magnitude or 0) >= SIGNIFICANT_MAGNITUDE
        and _distance_of(event) <= NEARBY_EVENT_METERS
    ]
    if strong:
        worst = max(strong, key=lambda event: event.magnitude or 0)
        return 2, AssessmentFactor(
            label="Strong earthquake nearby",
            detail=(
                f"Magnitude {worst.magnitude:.1f} {_distance_phrase(worst)} in "
                f"{_when(worst)}, from the USGS catalogue. "
                f"{len(disasters.events)} events on record within {radius_km} km."
            ),
            impact="negative",
        )

    # Nothing severe on record. Name the hazards that recur rather than every
    # type present: eight hazards listed alphabetically read as a tag dump and
    # buried whichever one actually happens here.
    return 1, AssessmentFactor(
        label="Events on record nearby",
        detail=(
            f"{len(disasters.events)} within {radius_km} km over "
            f"{disasters.searched_years} years, mostly {_common_hazards(disasters)}. "
            "None with recorded casualties."
        ),
        impact="neutral",
    )


def _describe_hazards(readings: list[HazardReading]) -> str:
    """Name hazards, noting distance for the ones found nearby rather than here.

    A tsunami band 300 m away is a different statement from one underfoot, and
    collapsing them would overstate one and understate the other.
    """
    parts: list[str] = []
    for reading in readings:
        label = reading.label.lower()
        if reading.within_meters is not None and reading.within_meters >= 1:
            parts.append(f"{label} ({round(reading.within_meters)} m away)")
        else:
            parts.append(f"{label} (here)")

    if len(parts) == 1:
        return parts[0]
    return f"{', '.join(parts[:-1])} and {parts[-1]}"


def _hazard_factor(hazards: HazardIndex) -> tuple[int, AssessmentFactor | None]:
    """Non-flood InaRISK hazards, folded into one factor.

    Flood is scored separately via the flood section, so counting it here too
    would double-weight the same reading.
    """
    answered = [
        reading
        for reading in hazards.readings
        if reading.key in SECONDARY_HAZARDS and reading.status == "ok"
    ]
    if not answered:
        return 0, None

    # A high hazard band 5 km away is context, not a property of this plot, so
    # only readings at or very near the plot move the concern level. The rest
    # still surface in the hazard section with their distance.
    scored = [
        reading
        for reading in answered
        if (reading.within_meters or 0) <= AT_PLOT_METERS
    ]
    nearby_only = [reading for reading in answered if reading not in scored]

    if not scored:
        strong = [r for r in nearby_only if r.level in {"high", "medium"}]
        if not strong:
            return 0, None
        return 0, AssessmentFactor(
            label="Hazard zones in the area",
            detail=(
                f"InaRISK maps {_describe_hazards(strong)} near this plot rather than on "
                "it, but worth knowing about the surroundings."
            ),
            impact="neutral",
        )

    high = [r for r in scored if r.level == "high"]
    medium = [r for r in scored if r.level == "medium"]

    if high:
        return 2, AssessmentFactor(
            label="High hazard in BNPB's model",
            detail=f"InaRISK rates {_describe_hazards(high)} as high.",
            impact="negative",
        )

    if medium:
        return 1, AssessmentFactor(
            label="Moderate hazard in BNPB's model",
            detail=f"InaRISK rates {_describe_hazards(medium)} as moderate.",
            impact="negative",
        )

    # Name what was actually rated. Crediting "hazards are low" off a single
    # answered layer would overstate how much BNPB really told us.
    return 0, AssessmentFactor(
        label="Low hazard in BNPB's model",
        detail=(
            f"InaRISK rates {_describe_hazards(scored)} as low. "
            "Other layers had no reading."
        ),
        impact="positive",
    )


def _access_factor(places: NearbyPlaces) -> tuple[int, AssessmentFactor | None]:
    """Access to essential services. Never raises the concern level.

    Poor access is a liveability problem, not a hazard, so this can only add
    context or credit — it must not turn a safe plot into a "higher concern" one.
    """
    if not places.categories:
        return 0, None

    essentials = {"health", "education", "shopping"}
    present = {category.key for category in places.categories} & essentials

    if len(present) == len(essentials):
        nearest = min(
            (c.nearest for c in places.categories if c.key in essentials and c.nearest),
            key=lambda place: place.distance_meters,
        )
        return 0, AssessmentFactor(
            label="Well served",
            detail=(
                f"Health, schools and shops are all mapped within "
                f"{places.radius_meters // 1000} km. The nearest is {nearest.name} "
                f"at {round(nearest.distance_meters)} m."
            ),
            impact="positive",
        )

    missing = sorted(essentials - present)
    return 0, AssessmentFactor(
        label="Sparse amenities",
        detail=(
            f"Nothing mapped nearby for: {', '.join(missing)}. That may just mean "
            "OpenStreetMap coverage is thin here."
        ),
        impact="neutral",
    )


def _air_quality_factor(air: AirQuality) -> tuple[int, AssessmentFactor | None]:
    """Air quality. Always scores zero, and that is the whole point of it.

    The score stays zero for two reasons, both worth stating because the next
    person to read this will want to change it.

    The verdict is a statement about *land*. Flood hazard, terrain and seismic
    history are properties of the ground that will still be true next decade.
    An AQI is one hour at one station: AQI 180 over Jakarta on an August
    afternoon is weather and traffic, not a property of the parcel, and it will
    read 60 after a week of rain. Scoring it would make the verdict change
    between two checks of the same plot while nothing about the plot changed.

    And it is measured somewhere else. WAQI answers with the nearest monitor,
    which may be 30 km away and on the other side of a city, so the reading that
    would be moving the verdict is often not a reading of this place at all.

    The factor is still shown, because a reader deciding where to live should
    see it. It just does not pretend to be a fact about the soil.
    """
    if air.status != "ok" or air.aqi is None or not air.band_label:
        return 0, None

    if air.band in ("unhealthy", "veryUnhealthy", "hazardous"):
        impact = "negative"
    elif air.band == "good":
        impact = "positive"
    else:
        impact = "neutral"

    where = ""
    if air.station_distance_meters is not None:
        where = f", measured {air.station_distance_meters / 1000:.0f} km away"

    driver = f" {air.dominant_label} is driving it." if air.dominant_label else ""

    return 0, AssessmentFactor(
        label=f"Air quality {air.band_label.lower()}",
        detail=(
            f"AQI {air.aqi} on the US EPA scale{where}.{driver} This is one hour's "
            "reading rather than a pattern, so it does not move the verdict."
        ),
        impact=impact,  # type: ignore[arg-type]
    )


def _overall_confidence(*levels: ConfidenceLevel) -> ConfidenceLevel:
    ranking = {"none": 0, "low": 1, "medium": 2, "high": 3}
    scores = [ranking[level] for level in levels]
    if not scores:
        return "none"

    average = sum(scores) / len(scores)
    if min(scores) == 0 and average < 1.5:
        return "none" if average == 0 else "low"
    if average >= 2.5:
        return "high"
    if average >= 1.5:
        return "medium"
    return "low"


def build_assessment(
    terrain: TerrainInfo,
    flood: FloodInfo,
    disasters: DisasterHistory,
    hazards: HazardIndex,
    places: NearbyPlaces,
    air_quality: AirQuality,
) -> Assessment:
    """Fold every section into one coarse, explainable verdict."""
    flood_score, flood_factor = _flood_factor(flood)
    terrain_score, terrain_factor = _terrain_factor(terrain)
    disaster_score, disaster_factor = _disaster_factor(disasters)
    tsunami_score, tsunami_factor = _tsunami_factor(disasters)
    hazard_score, hazard_factor = _hazard_factor(hazards)
    _, access_factor = _access_factor(places)
    _, air_factor = _air_quality_factor(air_quality)

    factors = [
        factor
        for factor in (
            flood_factor,
            hazard_factor,
            terrain_factor,
            disaster_factor,
            tsunami_factor,
            access_factor,
            air_factor,
        )
        if factor
    ]
    confidence = _overall_confidence(
        terrain.confidence, flood.confidence, disasters.confidence, hazards.confidence
    )

    if confidence == "none":
        return Assessment(
            level="unknown",
            headline=HEADLINES["unknown"],
            factors=factors,
            confidence="none",
        )

    total = flood_score + terrain_score + disaster_score + tsunami_score + hazard_score
    level: AssessmentLevel = "higher" if total >= 4 else "moderate" if total >= 2 else "low"

    return Assessment(
        level=level,
        headline=HEADLINES[level],
        factors=factors,
        confidence=confidence,
    )
