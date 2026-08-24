"""PostGIS-backed tables.

Kept deliberately small: only the layers a location report actually reads.
Everything here is optional — the API works with an empty (or absent) database.
"""

from __future__ import annotations

from datetime import datetime

from geoalchemy2 import Geometry, WKBElement
from sqlalchemy import (
    ARRAY,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for every spatial table."""


class LocationCache(Base):
    """Places we have already geocoded, so repeat lookups skip the provider."""

    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(Text, default=None)
    province: Mapped[str | None] = mapped_column(String(128), default=None)
    country: Mapped[str | None] = mapped_column(String(128), default=None)
    source: Mapped[str] = mapped_column(String(64), default="nominatim")
    geom: Mapped[WKBElement] = mapped_column(Geometry("POINT", srid=4326))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("idx_locations_geom", "geom", postgresql_using="gist"),)


class DisasterEvent(Base):
    """One recorded natural-disaster event with a point location."""

    __tablename__ = "disaster_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    #: Provider-native id, used to avoid re-importing the same event.
    external_id: Mapped[str | None] = mapped_column(String(128), unique=True, default=None)
    #: Display label, possibly compound ("earthquake and tsunami").
    event_type: Mapped[str] = mapped_column(String(64))
    #: The atomic hazards this event involved. Membership tests use this, never
    #: `event_type`: Palu 2018 and Aceh 2004 were both quake and tsunami, and a
    #: single label cannot answer "has a tsunami reached here?" for either.
    hazard_types: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), default=list, server_default="{}"
    )
    #: Administrative area for records located by area, so one district cannot
    #: monopolise a report's list. NULL for measured epicentres.
    area_name: Mapped[str | None] = mapped_column(String(128), default=None)
    title: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    magnitude: Mapped[float | None] = mapped_column(Float, default=None)
    #: Normalised scale — mb | mw | ms | ml | md | m | other. Rows are only
    #: comparable on this; agencies label the same quake differently and BMKG
    #: publishes no scale at all (``m``).
    magnitude_scale: Mapped[str | None] = mapped_column(String(16), default=None)
    #: The provider's own wording, e.g. "mww". Kept so normalising is lossless.
    magnitude_scale_source: Mapped[str | None] = mapped_column(String(32), default=None)
    #: Hypocentre depth in km — decides whether a quake was felt at all.
    depth_km: Mapped[float | None] = mapped_column(Float, default=None)
    #: Modified Mercalli shaking intensity (1..12).
    intensity_mmi: Mapped[float | None] = mapped_column(Float, default=None)
    #: ``modelled`` (ShakeMap) or ``reported`` (people who felt it).
    intensity_basis: Mapped[str | None] = mapped_column(String(16), default=None)
    felt_reports: Mapped[int | None] = mapped_column(Integer, default=None)
    # Recorded human impact. Only loss databases (DIBI/DesInventar) fill these;
    # NULL means the source published no figure, which is not zero.
    deaths: Mapped[int | None] = mapped_column(Integer, default=None)
    missing: Mapped[int | None] = mapped_column(Integer, default=None)
    injured: Mapped[int | None] = mapped_column(Integer, default=None)
    displaced: Mapped[int | None] = mapped_column(Integer, default=None)
    houses_destroyed: Mapped[int | None] = mapped_column(Integer, default=None)
    houses_damaged: Mapped[int | None] = mapped_column(Integer, default=None)
    source: Mapped[str] = mapped_column(String(64))
    url: Mapped[str | None] = mapped_column(Text, default=None)
    #: ``point`` for a measured location, ``regional`` for an area centroid,
    #: ``provincial`` when only a whole province could be resolved. Kept per row
    #: because a single table mixes all three.
    scope: Mapped[str] = mapped_column(String(16), default="point")
    geom: Mapped[WKBElement] = mapped_column(Geometry("POINT", srid=4326))

    __table_args__ = (
        Index("idx_disaster_events_geom", "geom", postgresql_using="gist"),
        Index("idx_disaster_events_occurred_at", "occurred_at"),
        Index("idx_disaster_events_type", "event_type"),
    )


class AdminArea(Base):
    """An administrative boundary, joined to area-level disaster records.

    Without it, an imported record is only as precise as its district's
    centroid, and "within 25 km" tests the wrong thing: a district whose centre
    is 26 km away can still reach to within 3 km of a pin. With the polygon,
    the distance becomes the gap to the area's nearest edge — zero when the pin
    is inside it, which is also what makes a pin's own district rank first.
    """

    __tablename__ = "admin_areas"

    id: Mapped[int] = mapped_column(primary_key=True)
    #: Matches :attr:`DisasterEvent.area_name`.
    name: Mapped[str] = mapped_column(String(128))
    #: regency (kabupaten/kota) | province
    level: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(64), default="DesInventar boundaries")
    geom: Mapped[WKBElement] = mapped_column(Geometry("MULTIPOLYGON", srid=4326))

    __table_args__ = (
        Index("idx_admin_areas_geom", "geom", postgresql_using="gist"),
        Index("idx_admin_areas_name", "name"),
        UniqueConstraint("name", "level", name="uq_admin_areas_name_level"),
    )


class FloodZone(Base):
    """A mapped flood-hazard polygon. Authoritative when it exists."""

    __tablename__ = "flood_zones"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255), default=None)
    #: "low" | "medium" | "high" — matches the API's RiskLevel values.
    risk_level: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(64))
    geom: Mapped[WKBElement] = mapped_column(Geometry("MULTIPOLYGON", srid=4326))

    __table_args__ = (Index("idx_flood_zones_geom", "geom", postgresql_using="gist"),)


class Waterway(Base):
    """Rivers, streams and canals used for the "how close is water" signal."""

    __tablename__ = "waterways"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255), default=None)
    #: OSM-style value: river, stream, canal, drain…
    kind: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(64), default="osm")
    geom: Mapped[WKBElement] = mapped_column(Geometry("MULTILINESTRING", srid=4326))

    __table_args__ = (Index("idx_waterways_geom", "geom", postgresql_using="gist"),)


class HazardCell(Base):
    """One InaRISK raster cell, ingested as a square polygon.

    BNPB serves its hazard models as ArcGIS ImageServers at 100 m resolution.
    Sampling them once into PostGIS turns a slow, frequently-unavailable remote
    call into a local `ST_Intersects` lookup — see `scripts/import_inarisk.py`.
    """

    __tablename__ = "hazard_cells"

    id: Mapped[int] = mapped_column(primary_key=True)
    #: flood | flashFlood | landslide | earthquake | tsunami
    hazard_type: Mapped[str] = mapped_column(String(32))
    #: The raw 0..1 index, kept alongside the class so nothing is lost.
    hazard_index: Mapped[float] = mapped_column(Float)
    #: low | medium | high, using BNPB's equal-thirds classification.
    risk_level: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(64), default="BNPB InaRISK")
    resolution_meters: Mapped[int] = mapped_column(Integer)
    #: Stable grid identity, so re-ingesting an overlapping area upserts.
    cell_key: Mapped[str] = mapped_column(String(64))
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    geom: Mapped[WKBElement] = mapped_column(Geometry("POLYGON", srid=4326))

    __table_args__ = (
        Index("idx_hazard_cells_geom", "geom", postgresql_using="gist"),
        Index("idx_hazard_cells_type", "hazard_type"),
        UniqueConstraint("hazard_type", "cell_key", name="uq_hazard_cells_type_cell"),
    )


class HazardCoverage(Base):
    """Which areas have been sampled, per hazard.

    Without this, an absent `hazard_cells` row is ambiguous: it could mean "the
    model says no hazard here" or "we never ingested this area". The first is an
    authoritative answer, the second needs a live call — and guessing wrong
    either way costs a slow request to BNPB or invents certainty we don't have.
    """

    __tablename__ = "hazard_coverage"

    id: Mapped[int] = mapped_column(primary_key=True)
    hazard_type: Mapped[str] = mapped_column(String(32))
    resolution_meters: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(64), default="BNPB InaRISK")
    #: Deterministic key for the ingested bounding box, so re-runs upsert.
    bbox_key: Mapped[str] = mapped_column(String(96))
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    geom: Mapped[WKBElement] = mapped_column(Geometry("POLYGON", srid=4326))

    __table_args__ = (
        Index("idx_hazard_coverage_geom", "geom", postgresql_using="gist"),
        UniqueConstraint("hazard_type", "bbox_key", name="uq_hazard_coverage_type_bbox"),
    )


class ElevationPoint(Base):
    """Sampled elevations, used as a cache/offline source for terrain."""

    __tablename__ = "elevation_points"

    id: Mapped[int] = mapped_column(primary_key=True)
    elevation_m: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(64))
    geom: Mapped[WKBElement] = mapped_column(Geometry("POINT", srid=4326))

    __table_args__ = (Index("idx_elevation_points_geom", "geom", postgresql_using="gist"),)
