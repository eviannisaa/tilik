"""Spatial reads against PostGIS.

Every function answers "what do we know locally?" and returns ``None``/empty
when the database is absent, empty, or unreachable — never an exception.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from geoalchemy2 import Geography
from sqlalchemy import case, cast, func, or_, select, text

from api.db.session import session_scope
from api.models import (
    AdminArea,
    DisasterEvent,
    ElevationPoint,
    FloodZone,
    HazardCell,
    HazardCoverage,
    Waterway,
)
from api.schemas.location import DisasterEvent as DisasterEventSchema
from api.schemas.location import DisasterImpact, WaterFeature

logger = logging.getLogger("tilik.db.repository")


@dataclass(frozen=True)
class HazardCellReading:
    """One ingested InaRISK hazard value at or near a point."""

    hazard_type: str
    hazard_index: float
    risk_level: str
    source: str
    resolution_meters: int
    #: Metres from the queried point; 0 when the point is inside the cell.
    distance_meters: float = 0.0


@dataclass(frozen=True)
class LocalAnalysis:
    """Everything PostGIS can say about a point, from a single query."""

    hazards: dict[str, HazardCellReading] = field(default_factory=dict)
    #: Hazards whose area has been ingested. A hazard listed here but absent
    #: from `hazards` genuinely has no modelled hazard at this point — no live
    #: call needed.
    covered_hazards: frozenset[str] = frozenset()
    flood_zone: tuple[str | None, str] | None = None
    nearest_water: WaterFeature | None = None
    elevation: float | None = None
    disasters: list[DisasterEventSchema] = field(default_factory=list)

    @property
    def has_any(self) -> bool:
        """Whether the database actually contributed anything for this point."""
        return bool(
            self.hazards
            or self.covered_hazards
            or self.flood_zone
            or self.nearest_water
            or self.elevation is not None
            or self.disasters
        )


def _point(latitude: float, longitude: float):
    """A 4326 point expression; PostGIS takes longitude first."""
    return func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326)


def _distance_basis(scope: str | None, area_matched: bool) -> str:
    """What a row's distance figure is measured to.

    Decides what may honestly be said about it. An edge distance is a lower
    bound — the event lies somewhere inside that area, so it cannot have been
    nearer. A centroid's is not a bound in either direction, so a row that fell
    back to one must not be presented as "at least this far".
    """
    if scope == "point":
        return "measured"
    return "area_edge" if area_matched else "area_centre"


#: The severity ordering, as SQL, for the two hand-written statements that need it.
#:
#: Distance alone cannot rank imported records. Every DIBI event in a regency
#: shares that regency's boundary, so they tie *exactly*: 176 rows sit the same
#: distance from a pin on Banda Aceh's beach, and with a plain `ORDER BY
#: distance` the tie breaks however Postgres feels. That let a house fire with no
#: casualties outrank the 2004 tsunami — 128,728 deaths — and pushed it out of
#: the list entirely.
#:
#: Ranked by who was harmed, then by recency, so ties resolve the same way on
#: every run. NULL is coalesced because Postgres puts it first under DESC, which
#: would let an unrecorded death toll outrank a known one.
#:
#: One definition rather than two: `disasters_near` and `_ANALYSE_LOCATION` are
#: both raw SQL, and the drift between them is exactly what a shared constant
#: prevents.
_SEVERITY_COLUMNS = ("deaths", "missing", "displaced", "houses_destroyed")


def _severity_order_sql(alias: str = "") -> str:
    """The ORDER BY terms, worst first, qualified by a table alias if given."""
    prefix = f"{alias}." if alias else ""
    harmed = ", ".join(f"COALESCE({prefix}{column}, 0) DESC" for column in _SEVERITY_COLUMNS)
    return f"{harmed}, {prefix}occurred_at DESC NULLS LAST"


#: Impact columns, in the order the schemas declare them.
_IMPACT_FIELDS = (
    "deaths",
    "missing",
    "injured",
    "displaced",
    "houses_destroyed",
    "houses_damaged",
)


def _impact(get) -> DisasterImpact | None:
    """Build an impact block, or ``None`` when the row carries no figures.

    ``get`` reads one column by name. An all-NULL row must produce ``None``
    rather than a block of zeros — "no figure published" and "nobody was hurt"
    are different claims, and only loss databases make the second one.
    """
    values = {name: get(name) for name in _IMPACT_FIELDS}
    if all(value is None for value in values.values()):
        return None
    return DisasterImpact(
        **{name: int(value) for name, value in values.items() if value is not None}
    )


async def nearest_waterway(
    latitude: float, longitude: float, radius_meters: int
) -> WaterFeature | None:
    """Closest mapped river/stream/canal within ``radius_meters``."""
    point = cast(_point(latitude, longitude), Geography)
    distance = func.ST_Distance(cast(Waterway.geom, Geography), point).label("distance")

    statement = (
        select(Waterway.name, Waterway.kind, distance)
        .where(func.ST_DWithin(cast(Waterway.geom, Geography), point, radius_meters))
        .order_by(distance)
        .limit(1)
    )

    async with session_scope() as session:
        if session is None:
            return None
        try:
            row = (await session.execute(statement)).first()
        except Exception as exc:  # noqa: BLE001
            logger.warning("nearest_waterway failed: %s", exc)
            return None

    if row is None:
        return None
    return WaterFeature(name=row.name, kind=row.kind, distance_meters=float(row.distance))


async def flood_zone_at(latitude: float, longitude: float) -> tuple[str | None, str] | None:
    """The mapped flood zone containing the point, as ``(name, risk_level)``."""
    point = _point(latitude, longitude)
    # If zones overlap, the most severe one wins.
    severity = case(
        (FloodZone.risk_level == "high", 3),
        (FloodZone.risk_level == "medium", 2),
        (FloodZone.risk_level == "low", 1),
        else_=0,
    )

    statement = (
        select(FloodZone.name, FloodZone.risk_level)
        .where(func.ST_Intersects(FloodZone.geom, point))
        .order_by(severity.desc())
        .limit(1)
    )

    async with session_scope() as session:
        if session is None:
            return None
        try:
            row = (await session.execute(statement)).first()
        except Exception as exc:  # noqa: BLE001
            logger.warning("flood_zone_at failed: %s", exc)
            return None

    return (row.name, row.risk_level) if row else None


async def disasters_near(
    latitude: float,
    longitude: float,
    radius_meters: int,
    years: int,
    limit: int = 20,
    per_area: int = 3,
) -> list[DisasterEventSchema]:
    """Locally stored disaster events around the point, nearest first.

    ``per_area`` caps how many rows any one administrative area contributes.
    Imported records share their district's centroid, so without it the nearest
    district takes the entire result: Kota Jakarta Selatan holds 105 rows 16 km
    from Serpong, enough to fill any limit on its own and hide every neighbour —
    including the district the pin is inside.
    """
    # Spatial filter first, ranking second — and each branch shaped so an index
    # can serve it.
    #
    # The previous form asked PostGIS for
    # `ST_DWithin(COALESCE(a.geom, d.geom)::geography, ...)` over a window
    # function computed across the whole table. Neither half could use an index:
    # the distance expression spans two tables, so it is not any one column, and
    # the ranking had nothing to narrow it. The plan was a sequential scan of
    # 32,447 rows, evaluating a geography predicate against regency polygons
    # 6,841 times to keep 144 — 7.5 seconds, which on its own put the report
    # past the 20-second timeout the frontend gives it.
    #
    # Split by what each row's distance actually measures, it drops to 0.4s:
    # measured events test their own point against the GIST index; area records
    # find the handful of regencies near the pin first (460 rows, indexed) and
    # then look their events up by name; and the few areas with no boundary fall
    # back to a centroid.
    statement = text(
        f"""
WITH ptg AS (
    SELECT ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography AS g
),
near_areas AS (
    SELECT a.name, ST_Distance(a.geom::geography, p.g) AS distance
    FROM admin_areas a, ptg p
    WHERE a.level = 'regency'
      AND ST_DWithin(a.geom::geography, p.g, :radius)
),
candidates AS (
    SELECT d.id, ST_Distance(d.geom::geography, p.g) AS distance, false AS area_matched
    FROM disaster_events d, ptg p
    WHERE d.scope = 'point'
      AND d.geom IS NOT NULL
      AND ST_DWithin(d.geom::geography, p.g, :radius)
    UNION ALL
    -- Regency rows only: a province outline would make its records match almost
    -- any pin inside it, and some names exist at both levels (Gorontalo is a
    -- regency and a province), so the row's own scope decides which is meant.
    SELECT d.id, na.distance, true AS area_matched
    FROM disaster_events d
    JOIN near_areas na ON na.name = d.area_name
    WHERE d.scope = 'regional'
    UNION ALL
    SELECT d.id, ST_Distance(d.geom::geography, p.g) AS distance, false AS area_matched
    FROM disaster_events d, ptg p
    WHERE d.scope <> 'point'
      AND d.geom IS NOT NULL
      AND (
          d.scope <> 'regional'
          OR NOT EXISTS (
              SELECT 1 FROM admin_areas a
              WHERE a.level = 'regency' AND a.name = d.area_name
          )
      )
      AND ST_DWithin(d.geom::geography, p.g, :radius)
),
ranked AS (
    SELECT d.*, c.distance, c.area_matched,
           row_number() OVER (
               PARTITION BY COALESCE(d.area_name, 'measured-' || d.id), d.event_type
               ORDER BY {_severity_order_sql("d")}
           ) AS rank_in_area
    FROM disaster_events d
    JOIN candidates c ON c.id = d.id
    -- Applied before the ranking, not after. Ranked first, an out-of-window row
    -- consumed a slot the cap then counted: Bogor's earthquakes rank a 1998
    -- record first, so a cap of three delivered two and dropped a 2012 event
    -- that was inside the window.
    WHERE d.occurred_at IS NULL OR d.occurred_at >= :since
)
SELECT * FROM ranked
WHERE rank_in_area <= :per_area
ORDER BY distance, {_severity_order_sql()}
LIMIT :limit
"""
    ).bindparams(
        lat=latitude,
        lng=longitude,
        radius=radius_meters,
        since=datetime.now(UTC) - timedelta(days=365 * years),
        per_area=per_area,
        limit=limit,
    )

    async with session_scope() as session:
        if session is None:
            return []
        try:
            rows = (await session.execute(statement)).all()
        except Exception as exc:  # noqa: BLE001
            logger.warning("disasters_near failed: %s", exc)
            return []

    return [
        DisasterEventSchema(
            id=row.external_id or f"db-{row.id}",
            type=row.event_type,
            hazard_types=list(row.hazard_types or ()),
            area_name=row.area_name,
            title=row.title,
            occurred_at=row.occurred_at.isoformat() if row.occurred_at else None,
            magnitude=row.magnitude,
            magnitude_scale=row.magnitude_scale,
            magnitude_scale_source=row.magnitude_scale_source,
            depth_km=row.depth_km,
            intensity_mmi=row.intensity_mmi,
            intensity_basis=row.intensity_basis,
            felt_reports=row.felt_reports,
            impact=_impact(row._mapping.get),
            distance_meters=float(row.distance),
            distance_basis=_distance_basis(row.scope, bool(row.area_matched)),
            source=row.source,
            url=row.url,
            scope=row.scope,
        )
        for row in rows
    ]


async def quake_losses_near(
    latitude: float,
    longitude: float,
    radius_meters: int,
    moments: list[datetime],
    hours: int,
) -> list[DisasterEventSchema]:
    """Imported earthquake records that belong to the given shocks.

    A targeted lookup, not a slice of the display pool. The matcher needs to
    know whether a loss record exists for a shock, and asking the display query
    to carry it was unreliable: a district's rows are capped and ranked by harm,
    so Bogor's earthquake with no recorded deaths sat below its landslides and
    fell outside the candidate limit — while the USGS shock of the same day
    stayed, unpaired. Whether two records describe one event cannot depend on
    how many other rows happened to fit.

    Matched on the area's own boundary where there is one, and on a date window
    wide enough for DIBI's local dates against USGS's UTC.
    """
    if not moments:
        return []

    point = cast(_point(latitude, longitude), Geography)
    extent = func.coalesce(AdminArea.geom, DisasterEvent.geom)
    window = timedelta(hours=hours)

    near_any = or_(
        *[
            DisasterEvent.occurred_at.between(moment - window, moment + window)
            for moment in moments
        ]
    )

    statement = (
        select(
            DisasterEvent.id,
            DisasterEvent.external_id,
            DisasterEvent.event_type,
            DisasterEvent.hazard_types,
            DisasterEvent.area_name,
            DisasterEvent.title,
            DisasterEvent.occurred_at,
            DisasterEvent.magnitude,
            DisasterEvent.magnitude_scale,
            DisasterEvent.magnitude_scale_source,
            DisasterEvent.depth_km,
            DisasterEvent.intensity_mmi,
            DisasterEvent.intensity_basis,
            DisasterEvent.felt_reports,
            DisasterEvent.deaths,
            DisasterEvent.missing,
            DisasterEvent.injured,
            DisasterEvent.displaced,
            DisasterEvent.houses_destroyed,
            DisasterEvent.houses_damaged,
            DisasterEvent.source,
            DisasterEvent.url,
            DisasterEvent.scope,
            func.ST_Distance(cast(extent, Geography), point).label("distance"),
            (AdminArea.id.isnot(None)).label("area_matched"),
        )
        .outerjoin(
            AdminArea,
            (AdminArea.name == DisasterEvent.area_name)
            & (AdminArea.level == "regency")
            & (DisasterEvent.scope == "regional"),
        )
        .where(DisasterEvent.event_type.in_(("earthquake", "earthquake and tsunami")))
        .where(func.ST_DWithin(cast(extent, Geography), point, radius_meters))
        .where(near_any)
        .order_by(func.ST_Distance(cast(extent, Geography), point))
    )

    async with session_scope() as session:
        if session is None:
            return []
        try:
            rows = (await session.execute(statement)).all()
        except Exception as exc:  # noqa: BLE001
            logger.warning("quake_losses_near failed: %s", exc)
            return []

    return [
        DisasterEventSchema(
            id=row.external_id or f"db-{row.id}",
            type=row.event_type,
            hazard_types=list(row.hazard_types or ()),
            area_name=row.area_name,
            title=row.title,
            occurred_at=row.occurred_at.isoformat() if row.occurred_at else None,
            magnitude=row.magnitude,
            magnitude_scale=row.magnitude_scale,
            magnitude_scale_source=row.magnitude_scale_source,
            depth_km=row.depth_km,
            intensity_mmi=row.intensity_mmi,
            intensity_basis=row.intensity_basis,
            felt_reports=row.felt_reports,
            impact=_impact(row._mapping.get),
            distance_meters=float(row.distance),
            distance_basis=_distance_basis(row.scope, bool(row.area_matched)),
            source=row.source,
            url=row.url,
            scope=row.scope,
        )
        for row in rows
    ]


async def nearest_elevation(
    latitude: float, longitude: float, radius_meters: int = 500
) -> float | None:
    """A sampled elevation near the point, if we've stored one."""
    point = cast(_point(latitude, longitude), Geography)
    distance = func.ST_Distance(cast(ElevationPoint.geom, Geography), point).label("distance")

    statement = (
        select(ElevationPoint.elevation_m, distance)
        .where(func.ST_DWithin(cast(ElevationPoint.geom, Geography), point, radius_meters))
        .order_by(distance)
        .limit(1)
    )

    async with session_scope() as session:
        if session is None:
            return None
        try:
            row = (await session.execute(statement)).first()
        except Exception as exc:  # noqa: BLE001
            logger.warning("nearest_elevation failed: %s", exc)
            return None

    return float(row.elevation_m) if row else None


async def hazard_near(
    latitude: float, longitude: float, radius_meters: int
) -> dict[str, HazardCellReading]:
    """Strongest ingested hazard of each type within ``radius_meters``.

    A radius rather than an exact hit because several InaRISK layers (tsunami,
    coastal erosion) are thin bands along the shoreline: a point a few hundred
    metres inland sits outside every cell, yet the hazard plainly matters.
    """
    point = cast(_point(latitude, longitude), Geography)
    distance = func.ST_Distance(cast(HazardCell.geom, Geography), point).label("distance")

    statement = (
        select(
            HazardCell.hazard_type,
            HazardCell.hazard_index,
            HazardCell.risk_level,
            HazardCell.source,
            HazardCell.resolution_meters,
            distance,
        )
        .where(func.ST_DWithin(cast(HazardCell.geom, Geography), point, radius_meters))
        # A cell containing the point is authoritative; otherwise take the
        # strongest nearby one. Mirrors the live sampling rule exactly.
        .order_by(
            HazardCell.hazard_type,
            case((distance == 0, 0), else_=1),
            HazardCell.hazard_index.desc(),
            distance,
        )
    )

    async with session_scope() as session:
        if session is None:
            return {}
        try:
            rows = (await session.execute(statement)).all()
        except Exception as exc:  # noqa: BLE001
            logger.warning("hazard_near failed: %s", exc)
            return {}

    readings: dict[str, HazardCellReading] = {}
    for row in rows:
        readings.setdefault(
            row.hazard_type,
            HazardCellReading(
                hazard_type=row.hazard_type,
                hazard_index=float(row.hazard_index),
                risk_level=row.risk_level,
                source=row.source,
                resolution_meters=int(row.resolution_meters),
                distance_meters=float(row.distance),
            ),
        )
    return readings


async def hazard_coverage_at(latitude: float, longitude: float) -> frozenset[str]:
    """Hazards whose ingested area contains this point."""
    point = _point(latitude, longitude)
    statement = (
        select(HazardCoverage.hazard_type)
        .where(func.ST_Intersects(HazardCoverage.geom, point))
        .distinct()
    )

    async with session_scope() as session:
        if session is None:
            return frozenset()
        try:
            rows = (await session.execute(statement)).scalars().all()
        except Exception as exc:  # noqa: BLE001
            logger.warning("hazard_coverage_at failed: %s", exc)
            return frozenset()

    return frozenset(rows)


async def archived_hazard_types() -> frozenset[str]:
    """Every hazard the imported archive can answer for, anywhere in Indonesia.

    This is deliberately *not* derived from the rows a given point returns.
    Coverage is a property of the catalogue, not of the answer: a pin with no
    eruption on record was still checked against 245 eruption records, and
    saying "volcanic eruption: not searched here" because none came back turns a
    genuine all-clear into a false gap in the search. Absence of a row means
    nothing was recorded nearby; only an absence from *this* set means the
    hazard was never looked for.
    """
    statement = select(func.unnest(DisasterEvent.hazard_types)).distinct()

    async with session_scope() as session:
        if session is None:
            return frozenset()
        try:
            rows = (await session.execute(statement)).scalars().all()
        except Exception as exc:  # noqa: BLE001
            logger.warning("archived_hazard_types failed: %s", exc)
            return frozenset()

    return frozenset(hazard for hazard in rows if hazard)


#: One statement covering every spatial question a report asks.
#:
#: Each CTE is independent, so PostGIS answers hazards, flood zone, nearest
#: waterway, nearest elevation sample and disaster events in a single round
#: trip. `hz` and `ev` aggregate, so they always yield exactly one row; the rest
#: are LEFT JOINed onto that so a miss produces NULLs rather than no result.
_ANALYSE_LOCATION = text(
    f"""
WITH pt AS (
    SELECT ST_SetSRID(ST_MakePoint(:lng, :lat), 4326) AS geom
),
ptg AS (
    SELECT geom::geography AS g FROM pt
),
hz AS (
    -- Strongest cell of each hazard type within the search radius, plus how far
    -- away it is. DISTINCT ON + ORDER BY picks the peak per type in one pass.
    SELECT jsonb_agg(to_jsonb(peak) ORDER BY peak.hazard_type) AS hazards
    FROM (
        SELECT DISTINCT ON (h.hazard_type)
               h.hazard_type,
               h.hazard_index,
               h.risk_level,
               h.source,
               h.resolution_meters,
               ST_Distance(h.geom::geography, ptg.g) AS distance
        FROM hazard_cells h, ptg
        WHERE ST_DWithin(h.geom::geography, ptg.g, :hazard_radius)
        -- A cell containing the point wins; otherwise the strongest nearby.
        ORDER BY h.hazard_type,
                 (ST_Distance(h.geom::geography, ptg.g) > 0),
                 h.hazard_index DESC,
                 distance
    ) AS peak
),
cov AS (
    SELECT array_agg(DISTINCT c.hazard_type) AS covered
    FROM hazard_coverage c, pt
    WHERE ST_Intersects(c.geom, pt.geom)
),
fz AS (
    SELECT f.name AS zone_name, f.risk_level AS zone_risk
    FROM flood_zones f, pt
    WHERE ST_Intersects(f.geom, pt.geom)
    ORDER BY CASE f.risk_level
                 WHEN 'high' THEN 3 WHEN 'medium' THEN 2 WHEN 'low' THEN 1 ELSE 0
             END DESC
    LIMIT 1
),
ww AS (
    SELECT w.name AS water_name,
           w.kind AS water_kind,
           ST_Distance(w.geom::geography, ptg.g) AS water_distance
    FROM waterways w, ptg
    WHERE ST_DWithin(w.geom::geography, ptg.g, :waterway_radius)
    ORDER BY water_distance
    LIMIT 1
),
el AS (
    SELECT e.elevation_m
    FROM elevation_points e, ptg
    WHERE ST_DWithin(e.geom::geography, ptg.g, :elevation_radius)
    ORDER BY ST_Distance(e.geom::geography, ptg.g)
    LIMIT 1
),
near_areas AS (
    -- The handful of regencies within reach, found first and once.
    --
    -- The event filter used to read
    -- `ST_DWithin(COALESCE(a.geom, d.geom)::geography, ...)`, an expression
    -- spanning two tables that no index can serve, over a window function
    -- computed across all 32,447 rows. PostGIS sequentially scanned the table
    -- and evaluated a geography predicate against regency polygons 6,841 times
    -- to keep 144: 7.5 seconds, enough on its own to put the report past the
    -- 20-second timeout the frontend allows it. Testing 460 indexed polygons
    -- once and then looking events up by name takes 0.4s.
    SELECT a.name, ST_Distance(a.geom::geography, ptg.g) AS distance
    FROM admin_areas a
    CROSS JOIN ptg
    WHERE a.level = 'regency'
      AND ST_DWithin(a.geom::geography, ptg.g, :disaster_radius)
),
candidates AS (
    -- Split by what each row's distance actually measures, so each branch can
    -- use an index.
    SELECT d.id, ST_Distance(d.geom::geography, ptg.g) AS distance, false AS area_matched
    FROM disaster_events d
    CROSS JOIN ptg
    WHERE d.scope = 'point'
      AND d.geom IS NOT NULL
      AND ST_DWithin(d.geom::geography, ptg.g, :disaster_radius)
    UNION ALL
    -- Regency rows only. A province outline would make its records match almost
    -- any pin inside it — events in Kota Serang read as 0 km from Serpong,
    -- Pangandaran 250 km away read as 6 km — so a provincial row keeps its
    -- centroid and stays conservatively far. Some names exist at both levels
    -- (Gorontalo is a regency and a province), so scope decides which is meant.
    SELECT d.id, na.distance, true AS area_matched
    FROM disaster_events d
    JOIN near_areas na ON na.name = d.area_name
    WHERE d.scope = 'regional'
    UNION ALL
    -- The areas with no boundary in the source keep their centroid, and no bound
    -- can be claimed from it in either direction.
    SELECT d.id, ST_Distance(d.geom::geography, ptg.g) AS distance, false AS area_matched
    FROM disaster_events d
    CROSS JOIN ptg
    WHERE d.scope <> 'point'
      AND d.geom IS NOT NULL
      AND (
          d.scope <> 'regional'
          OR NOT EXISTS (
              SELECT 1 FROM admin_areas a
              WHERE a.level = 'regency' AND a.name = d.area_name
          )
      )
      AND ST_DWithin(d.geom::geography, ptg.g, :disaster_radius)
),
ev AS (
    SELECT jsonb_agg(to_jsonb(found) ORDER BY found.distance) AS events
    FROM (
        SELECT d.id,
               d.external_id,
               d.event_type,
               d.hazard_types,
               d.area_name,
               d.title,
               d.occurred_at,
               d.magnitude,
               d.magnitude_scale,
               d.magnitude_scale_source,
               d.depth_km,
               d.intensity_mmi,
               d.intensity_basis,
               d.felt_reports,
               d.deaths,
               d.missing,
               d.injured,
               d.displaced,
               d.houses_destroyed,
               d.houses_damaged,
               d.source,
               d.url,
               d.scope,
               d.distance,
               d.area_matched
        FROM (
            SELECT e.*,
                   c.distance,
                   c.area_matched,
                   row_number() OVER (
                       -- One partition per area *and hazard*, not per area
                       -- alone. Ranking a district's rows against each other
                       -- starved whole hazards: Bogor's 694 rows are mostly
                       -- landslides with 7-12 dead, so its one earthquake — no
                       -- deaths recorded — never survived a cap of 3, and the
                       -- matcher never saw the row that pairs with the USGS
                       -- shock of the same day. A measured row gets its own
                       -- partition, keyed on its id, so epicentres are never
                       -- capped.
                       PARTITION BY COALESCE(e.area_name, 'measured-' || e.id),
                                    e.event_type
                       ORDER BY {_severity_order_sql("e")}
                   ) AS rank_in_area
            FROM disaster_events e
            JOIN candidates c ON c.id = e.id
            -- Filtered before the ranking, not after. Ranked first, an
            -- out-of-window row consumed a slot the cap then counted: Bogor's
            -- earthquakes rank a 1998 record first, so a cap of three delivered
            -- two and dropped a 2012 event that was inside the window.
            WHERE e.occurred_at IS NULL OR e.occurred_at >= :since
        ) AS d
        -- Cap each administrative area before the row limit applies. Without
        -- this the whole candidate pool goes to one district: around Serpong,
        -- Kota Jakarta Selatan holds 105 rows at 16 km, so all 72 candidates
        -- were its own and the district the pin actually sits in never reached
        -- the selection step at all.
        WHERE d.rank_in_area <= :event_per_area
        -- Distance alone can't rank imported rows: every DIBI event in a
        -- regency shares one centroid, so they tie exactly and the worst event
        -- can be cut arbitrarily. See _severity_order().
        ORDER BY d.distance, {_severity_order_sql("d")}
        LIMIT :event_limit
    ) AS found
)
SELECT hz.hazards,
       cov.covered,
       fz.zone_name, fz.zone_risk,
       ww.water_name, ww.water_kind, ww.water_distance,
       el.elevation_m,
       ev.events
FROM hz
LEFT JOIN cov ON TRUE
LEFT JOIN fz ON TRUE
LEFT JOIN ww ON TRUE
LEFT JOIN el ON TRUE
LEFT JOIN ev ON TRUE
"""
)


async def analyse_location(
    latitude: float,
    longitude: float,
    *,
    waterway_radius_meters: int,
    disaster_radius_meters: int,
    disaster_years: int,
    event_limit: int,
    event_per_area: int,
    hazard_radius_meters: int,
    elevation_radius_meters: int = 150,
) -> LocalAnalysis | None:
    """Run every spatial lookup for a point in one PostGIS query.

    Returns ``None`` when there is no database, or when the query fails — for
    instance because `schema.sql` hasn't been applied. Callers fall back to
    external providers in that case.
    """
    since = datetime.now(UTC) - timedelta(days=365 * disaster_years)

    async with session_scope() as session:
        if session is None:
            return None
        try:
            row = (
                await session.execute(
                    _ANALYSE_LOCATION,
                    {
                        "lat": latitude,
                        "lng": longitude,
                        "waterway_radius": waterway_radius_meters,
                        "hazard_radius": hazard_radius_meters,
                        "elevation_radius": elevation_radius_meters,
                        "disaster_radius": disaster_radius_meters,
                        "since": since,
                        "event_limit": event_limit,
                        "event_per_area": event_per_area,
                    },
                )
            ).first()
        except Exception as exc:  # noqa: BLE001
            logger.warning("analyse_location failed, falling back to providers: %s", exc)
            return None

    if row is None:
        return None

    hazards = {
        entry["hazard_type"]: HazardCellReading(
            hazard_type=entry["hazard_type"],
            hazard_index=float(entry["hazard_index"]),
            risk_level=entry["risk_level"],
            source=entry["source"],
            resolution_meters=int(entry["resolution_meters"]),
            distance_meters=float(entry["distance"]),
        )
        for entry in (row.hazards or [])
    }

    water = None
    if row.water_distance is not None:
        water = WaterFeature(
            name=row.water_name,
            kind=row.water_kind,
            distance_meters=float(row.water_distance),
        )

    events = [
        DisasterEventSchema(
            id=entry.get("external_id") or f"db-{entry['id']}",
            type=entry["event_type"],
            hazard_types=list(entry.get("hazard_types") or ()),
            area_name=entry.get("area_name"),
            title=entry["title"],
            occurred_at=entry.get("occurred_at"),
            magnitude=entry.get("magnitude"),
            magnitude_scale=entry.get("magnitude_scale"),
            magnitude_scale_source=entry.get("magnitude_scale_source"),
            depth_km=entry.get("depth_km"),
            intensity_mmi=entry.get("intensity_mmi"),
            intensity_basis=entry.get("intensity_basis"),
            felt_reports=entry.get("felt_reports"),
            impact=_impact(entry.get),
            distance_meters=float(entry["distance"]),
            distance_basis=_distance_basis(
                entry.get("scope"), bool(entry.get("area_matched"))
            ),
            source=entry["source"],
            url=entry.get("url"),
            scope=entry.get("scope") or "point",
        )
        for entry in (row.events or [])
    ]

    return LocalAnalysis(
        hazards=hazards,
        covered_hazards=frozenset(row.covered or ()),
        flood_zone=(row.zone_name, row.zone_risk) if row.zone_risk else None,
        nearest_water=water,
        elevation=float(row.elevation_m) if row.elevation_m is not None else None,
        disasters=events,
    )
