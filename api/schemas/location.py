"""Location, search and single-topic response schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from api.schemas.common import (
    CamelModel,
    ConfidenceLevel,
    RiskLevel,
    TerrainKind,
)


class Coordinates(CamelModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class LocationInfo(CamelModel):
    latitude: float
    longitude: float
    name: str | None = None
    display_name: str | None = None
    locality: str | None = None
    district: str | None = None
    city: str | None = None
    province: str | None = None
    country: str | None = None
    postcode: str | None = None


class SearchResult(CamelModel):
    latitude: float
    longitude: float
    name: str
    display_name: str
    category: str | None = None
    #: [south, north, west, east] in degrees, when the provider supplies it.
    bounding_box: tuple[float, float, float, float] | None = None
    #: The administrative chain, when the provider gave one.
    #:
    #: `reverse` resolves these and used to discard them, so a checked point knew
    #: its street name and nothing about which kecamatan, kabupaten or province
    #: it sat in. Indonesia has more than one Serpong and more than one Palu, and
    #: the chain is what tells them apart.
    district: str | None = None
    city: str | None = None
    province: str | None = None


class SearchResponse(CamelModel):
    query: str
    results: list[SearchResult] = Field(default_factory=list)
    provider: str
    #: True when results came from the offline gazetteer instead of a geocoder.
    degraded: bool = False


class TerrainInfo(CamelModel):
    elevation: float | None = None
    unit: Literal["meters"] = "meters"
    terrain: TerrainKind = "unknown"
    description: str
    confidence: ConfidenceLevel = "none"


class WaterFeature(CamelModel):
    name: str | None = None
    kind: str
    distance_meters: float


class FloodInfo(CamelModel):
    risk: RiskLevel = "unknown"
    reason: str
    nearest_river: WaterFeature | None = None
    zone_name: str | None = None
    confidence: ConfidenceLevel = "none"
    #: BNPB InaRISK flood-hazard index (0..1) when that layer answered, whatever
    #: decided `risk`. Kept even when a mapped zone wins, because local data and
    #: the national model disagreeing is the most useful thing this section can
    #: say — and dropping the index hid exactly that case.
    hazard_index: float | None = None
    #: InaRISK's own class for that index. Sent rather than re-derived in the UI,
    #: so BNPB's 0.33/0.67 boundaries live in one place.
    hazard_level: RiskLevel | None = None
    #: Which source decided the risk level: postgis | inarisk | heuristic.
    basis: str = "heuristic"


#: Magnitude scales, normalised so two rows can be compared at all.
#:
#: Agencies label the same earthquake differently: USGS computes ``mb`` for
#: moderate Indonesian events and switches to ``mww`` above roughly 6.5 (``mb``
#: saturates there), while BMKG publishes a bare number with no scale at all —
#: that unlabelled case is ``m``. Storing the provider's raw string on its own
#: made the magnitude column silently incomparable, so the normalised value and
#: the provider's own wording are now kept apart.
MagnitudeScale = Literal["mb", "mw", "ms", "ml", "md", "m", "other"]


class DisasterImpact(CamelModel):
    """Recorded human impact, as the source counted it.

    Only loss databases carry this — a seismic catalogue never does. ``None``
    means the source has no figure, which is not the same as zero: DIBI records
    plenty of events with a real death toll and a blank displacement column.
    """

    deaths: int | None = None
    missing: int | None = None
    injured: int | None = None
    displaced: int | None = None
    houses_destroyed: int | None = None
    houses_damaged: int | None = None

    @property
    def has_any(self) -> bool:
        """Whether any figure was reported at all."""
        return any(
            value is not None
            for value in (
                self.deaths,
                self.missing,
                self.injured,
                self.displaced,
                self.houses_destroyed,
                self.houses_damaged,
            )
        )


class DisasterEvent(CamelModel):
    id: str
    #: Display label for the event. May be compound — "earthquake and tsunami" —
    #: because real events are. Never test hazard membership on this; use
    #: :attr:`hazard_types`.
    type: str
    #: The atomic hazards this one event involved, for membership tests and for
    #: :attr:`DisasterHistory.covered_types`.
    #:
    #: A single ``type`` string cannot answer "has a tsunami ever reached here?"
    #: for Palu 2018 or Aceh 2004, which were both. Filing them under
    #: ``tsunami`` hid them from earthquakes; filing them under a compound label
    #: hid them from both, and since an absent entry in ``covered_types`` means
    #: "never searched", that turned a 128,728-death tsunami into an implicit
    #: "no tsunami data here". Splitting the row in two would double-count every
    #: death, so the row stays whole and its hazards are listed.
    #:
    #: Defaults to ``[type]``, so a single-hazard source needs to do nothing.
    hazard_types: list[str] = Field(default_factory=list)
    #: The administrative area a record belongs to, e.g. "Kota Tangerang
    #: Selatan". Set for records located by area rather than measured; ``None``
    #: for a seismic epicentre, which belongs to a coordinate, not a district.
    area_name: str | None = None
    title: str
    occurred_at: str | None = None
    magnitude: float | None = None
    #: Normalised scale for ``magnitude``. Compare rows on this, never on
    #: :attr:`magnitude_scale_source`.
    magnitude_scale: MagnitudeScale | None = None
    #: Exactly what the provider called the scale, e.g. ``"mww"``. Kept for
    #: provenance so normalising never destroys what the source actually said.
    magnitude_scale_source: str | None = None
    #: Hypocentre depth. The single most useful number for whether a quake was
    #: felt: a magnitude 4.5 at 10 km shakes a town, the same magnitude at
    #: 194 km in the subducting slab reaches the surface as nothing.
    depth_km: float | None = None
    #: Shaking intensity on the Modified Mercalli scale (1..12). This, not
    #: magnitude, is what a reader can actually interpret — it describes the
    #: ground at a place rather than the energy at the source.
    intensity_mmi: float | None = None
    #: ``modelled`` for a ShakeMap estimate, ``reported`` when it comes from
    #: people who felt it. Both are intensity; only one is an observation.
    intensity_basis: Literal["modelled", "reported"] | None = None
    #: How many people filed a felt report. Coverage is thin outside the US —
    #: a low count is weak evidence of a quiet event, absence is no evidence.
    felt_reports: int | None = None
    impact: DisasterImpact | None = None
    distance_meters: float | None = None
    #: What :attr:`distance_meters` is a distance *to*, which decides what can
    #: honestly be said about it.
    #:
    #: ``measured`` — the event's own position. Exact.
    #: ``area_edge`` — the nearest edge of the area holding the record. The event
    #: lies somewhere inside, so the figure is a **lower bound**: it cannot have
    #: been nearer. Zero means the coordinate is inside the area.
    #: ``area_centre`` — a centroid, because that area has no boundary here. The
    #: event may be nearer or further, so no bound can be claimed.
    distance_basis: Literal["measured", "area_edge", "area_centre"] | None = None
    #: Height the water reached at this observation, in metres.
    #:
    #: Recorded per observation by NOAA/NCEI, which makes it the one tsunami
    #: figure that is genuinely local: 10.7 m at Palu says what happened at
    #: Palu. Casualty totals in the same database are per event, so they are not
    #: carried here — see :mod:`api.services.ncei_tsunami`.
    water_height_m: float | None = None
    source: str
    url: str | None = None
    #: ``point`` for a measured location like a seismic epicentre; ``regional``
    #: when the coordinate is a centroid for an affected area, so the distance
    #: is indicative rather than exact; ``provincial`` when even the area is a
    #: whole province, which makes the distance meaningless rather than merely
    #: approximate. Only ``point`` events feed the assessment's
    #: "significant events nearby" test.
    scope: Literal["point", "regional", "provincial"] = "point"
    #: Provider-native severity label, e.g. GDACS alert level.
    severity: str | None = None

    @model_validator(mode="after")
    def _default_hazard_types(self) -> DisasterEvent:
        """Fall back to the single hazard named by ``type``.

        Keeps every existing caller correct without change, and guarantees the
        list is never empty — an empty one would drop the event out of
        ``covered_types`` entirely, which is the failure this field exists to
        prevent.
        """
        if not self.hazard_types:
            self.hazard_types = [self.type]
        return self


class DisasterHistory(CamelModel):
    #: The radius every source was searched within. Nothing in the list can
    #: exceed it: the wider-reaching GDACS feed was removed.
    radius_meters: int
    events: list[DisasterEvent] = Field(default_factory=list)
    searched_years: int
    #: The earthquake radius, when it differs from :attr:`radius_meters`.
    #:
    #: Set whenever USGS answered over a wider reach than the archive, so a row
    #: reading "72 km from coordinate" cannot sit under a caption claiming the
    #: search stopped at 25 km.
    earthquake_radius_meters: int | None = None
    #: The tsunami window, when it differs from :attr:`searched_years`.
    #:
    #: Set only when NOAA/NCEI answered. Without it a 1883 tsunami would appear
    #: under a caption reading "last 25 years", which is a plain contradiction.
    tsunami_years: int | None = None
    confidence: ConfidenceLevel = "none"
    #: Catalogues actually queried, e.g. ["USGS", "BNPB DIBI (PostGIS)"].
    searched_sources: list[str] = Field(default_factory=list)
    #: Event types those catalogues can return. Anything absent here was never
    #: searched, so "no flood recorded" must not be read as "no flood happened".
    covered_types: list[str] = Field(default_factory=list)
    note: str | None = None


class NewsItem(CamelModel):
    """One published story about something that happened near this location."""

    id: str
    title: str
    url: str
    published_at: str | None = None
    #: Publisher, as the feed names it (e.g. "detikNews", "Kompas.com").
    source: str | None = None
    #: Hazard key shared with :mod:`api.services.inarisk`, so a story lines up
    #: with the matching row of the hazard index.
    topic: str
    topic_label: str


class LocalNews(CamelModel):
    """Recent reporting near a point.

    This is press coverage, not a hazard record: it says what was *reported*
    around a place name, which is why ``matched_area`` is always sent back — the
    reader has to be able to see how wide the net was.
    """

    items: list[NewsItem] = Field(default_factory=list)
    #: The place name actually searched, e.g. "Kota Tangerang Selatan".
    matched_area: str | None = None
    months_searched: int = 12
    #: ``no_area`` means we never had a place name to search on, which is a very
    #: different statement from ``no_results``.
    status: Literal["ok", "no_area", "no_results", "unavailable"] = "no_results"
    #: Distinct topic keys present, for filtering in the UI.
    topics: list[str] = Field(default_factory=list)
    note: str | None = None


class AreaFeature(CamelModel):
    name: str
    kind: str
    distance_meters: float | None = None


class AreaInfo(CamelModel):
    administrative_area: str | None = None
    country: str | None = None
    coordinates: Coordinates
    nearby_features: list[AreaFeature] = Field(default_factory=list)


class HazardReading(CamelModel):
    """One BNPB InaRISK hazard layer sampled at a point.

    ``status`` matters as much as ``index``: "the model has no hazard here" and
    "we couldn't reach the model" both produce a null index but mean opposite
    things to someone deciding whether to buy.
    """

    key: str
    label: str
    #: 0..1 hazard index. ``None`` unless ``status`` is ``ok``.
    index: float | None = None
    level: RiskLevel = "unknown"
    #: ``out_of_coverage`` matters as much as the rest: InaRISK models Indonesia
    #: only, and "outside the model" must never render as "no hazard here".
    status: Literal["ok", "no_data", "unavailable", "out_of_coverage"] = "unavailable"
    #: ``postgis`` when read from ingested cells, ``inarisk`` when fetched live.
    source: Literal["postgis", "inarisk", "none"] = "none"
    #: Grid resolution of the ingested cell, when it came from PostGIS.
    resolution_meters: int | None = None
    #: How far from the queried point the value was found. 0 means the point
    #: itself sits in the hazard area; a positive number means it's nearby.
    within_meters: float | None = None
    description: str


class HazardIndex(CamelModel):
    """The InaRISK multi-hazard readout for a point."""

    source: str = "BNPB InaRISK"
    readings: list[HazardReading] = Field(default_factory=list)
    confidence: ConfidenceLevel = "none"
    note: str | None = None


class NearbyPlace(CamelModel):
    """A single mapped facility near the point."""

    name: str
    #: OSM tag value: hospital, school, supermarket…
    kind: str
    category: str
    distance_meters: float


class PlaceCategory(CamelModel):
    """Facilities of one kind, nearest first."""

    key: str
    label: str
    count: int
    nearest: NearbyPlace | None = None
    places: list[NearbyPlace] = Field(default_factory=list)


class NearbyPlaces(CamelModel):
    """What is around the point — schools, clinics, shops, transport."""

    radius_meters: int
    total: int = 0
    categories: list[PlaceCategory] = Field(default_factory=list)
    confidence: ConfidenceLevel = "none"
    note: str | None = None


class HazardsResponse(CamelModel):
    latitude: float
    longitude: float
    hazards: HazardIndex


class PlacesResponse(CamelModel):
    latitude: float
    longitude: float
    places: NearbyPlaces


class ElevationResponse(CamelModel):
    latitude: float
    longitude: float
    terrain: TerrainInfo
    provider: str


class FloodRiskResponse(CamelModel):
    latitude: float
    longitude: float
    flood: FloodInfo


class DisastersResponse(CamelModel):
    latitude: float
    longitude: float
    disasters: DisasterHistory


class NewsResponse(CamelModel):
    latitude: float
    longitude: float
    news: LocalNews
