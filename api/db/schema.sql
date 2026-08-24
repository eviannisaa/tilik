-- Tilik spatial schema (PostgreSQL + PostGIS).
--
-- Run once against your database, e.g. on Supabase:
--   psql "$DATABASE_URL" -f api/db/schema.sql
--
-- Everything here is optional. The API answers with external/estimated data
-- when these tables are missing or empty.

CREATE EXTENSION IF NOT EXISTS postgis;

-- ---------------------------------------------------------------------------
-- locations: geocoding cache, so repeat lookups skip the external provider.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS locations (
    id            BIGSERIAL PRIMARY KEY,
    name          VARCHAR(255) NOT NULL,
    display_name  TEXT,
    province      VARCHAR(128),
    country       VARCHAR(128),
    source        VARCHAR(64) NOT NULL DEFAULT 'nominatim',
    geom          geometry(Point, 4326) NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_locations_geom ON locations USING GIST (geom);

-- ---------------------------------------------------------------------------
-- disaster_events: point-located historical events (quakes, floods, landslides).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS disaster_events (
    id             BIGSERIAL PRIMARY KEY,
    external_id    VARCHAR(128) UNIQUE,
    event_type     VARCHAR(64) NOT NULL,
    -- The atomic hazards one event involved. event_type is a display label and
    -- may be compound ('earthquake and tsunami'); membership tests use this
    -- array, so Palu 2018 and Aceh 2004 register under both 'earthquake' and
    -- 'tsunami' without the row being split and its death toll double-counted.
    hazard_types   TEXT[] NOT NULL DEFAULT '{}',
    -- Administrative area, for records located by area rather than measured.
    -- Without it one district monopolises a report: around Serpong, Kota
    -- Jakarta Selatan's centroid is 16 km away and Kota Tangerang Selatan's is
    -- 18 km, so Jakarta took 8 of 12 slots and the pin's own district showed
    -- nothing. NULL for a seismic epicentre, which belongs to a coordinate.
    area_name      VARCHAR(128),
    title          TEXT NOT NULL,
    occurred_at    TIMESTAMPTZ,
    magnitude      DOUBLE PRECISION,
    -- Normalised scale. Agencies label the same earthquake differently — USGS
    -- computes 'mb' for moderate Indonesian events and 'mww' above ~6.5, while
    -- BMKG publishes a bare number with no scale ('m'). Rows are only
    -- comparable on this column; magnitude_scale_source keeps the raw wording.
    magnitude_scale        VARCHAR(16)
                           CHECK (magnitude_scale IN
                                  ('mb','mw','ms','ml','md','m','other')),
    magnitude_scale_source VARCHAR(32),
    -- Hypocentre depth. Decides whether a quake was felt: magnitude 4.5 at
    -- 10 km shakes a town, the same at 194 km reaches the surface as nothing.
    depth_km       DOUBLE PRECISION,
    -- Modified Mercalli shaking intensity (1..12) — what a reader can actually
    -- interpret, unlike magnitude, because it describes the ground at a place.
    intensity_mmi  DOUBLE PRECISION CHECK (intensity_mmi BETWEEN 1 AND 12),
    intensity_basis VARCHAR(16)
                    CHECK (intensity_basis IN ('modelled', 'reported')),
    felt_reports   INTEGER,
    -- Recorded human impact. Only loss databases (BNPB DIBI / DesInventar)
    -- carry these; a seismic catalogue never does. NULL means the source
    -- published no figure, which is not the same as zero.
    deaths            INTEGER,
    missing           INTEGER,
    injured           INTEGER,
    displaced         INTEGER,
    houses_destroyed  INTEGER,
    houses_damaged    INTEGER,
    source         VARCHAR(64) NOT NULL,
    url            TEXT,
    -- 'point' for a measured location (a seismic epicentre); 'regional' when the
    -- coordinate is an area centroid, so distance from it is only indicative.
    -- 'provincial' is coarser than 'regional': the position is a whole
    -- province's centroid, so the distance is meaningless, not just rough.
    scope          VARCHAR(16) NOT NULL DEFAULT 'point'
                   CHECK (scope IN ('point', 'regional', 'provincial')),
    geom           geometry(Point, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_disaster_events_geom        ON disaster_events USING GIST (geom);
-- On the cast, not the column. Every distance here is metric, so the query says
-- `geom::geography`, and a GIST index over the plain geometry cannot serve that
-- expression: PostGIS fell back to a sequential scan of 32,447 rows.
CREATE INDEX IF NOT EXISTS idx_disaster_events_geog        ON disaster_events USING GIST ((geom::geography));
CREATE INDEX IF NOT EXISTS idx_disaster_events_occurred_at ON disaster_events (occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_disaster_events_type        ON disaster_events (event_type);

-- ---------------------------------------------------------------------------
-- admin_areas: administrative boundaries, so an area-level record can be tested
-- against its real extent instead of its centre.
--
-- Imported records carry no coordinate of their own, so they were placed at
-- their district's centroid and matched on the distance to that point. A
-- centroid is a poor stand-in for a district: one whose centre is 26 km away
-- can reach to within 3 km of a pin, and a pin can sit *inside* a district
-- whose centre is 19 km off. Joining to the boundary makes "within 25 km" mean
-- the area actually comes within 25 km, and makes the distance the gap to its
-- nearest edge — zero when the pin is inside it.
--
-- Filled by scripts/import_desinventar.py from the boundaries shipped with the
-- DesInventar export. `name` matches disaster_events.area_name.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS admin_areas (
    id      BIGSERIAL PRIMARY KEY,
    name    VARCHAR(128) NOT NULL,
    -- 'regency' (kabupaten/kota) or 'province'.
    level   VARCHAR(16) NOT NULL CHECK (level IN ('regency', 'province')),
    source  VARCHAR(64) NOT NULL DEFAULT 'DesInventar boundaries',
    geom    geometry(MultiPolygon, 4326) NOT NULL,
    CONSTRAINT uq_admin_areas_name_level UNIQUE (name, level)
);

CREATE INDEX IF NOT EXISTS idx_admin_areas_geom ON admin_areas USING GIST (geom);
-- Same reason as the events table: the boundary test is metric.
CREATE INDEX IF NOT EXISTS idx_admin_areas_geog ON admin_areas USING GIST ((geom::geography));
CREATE INDEX IF NOT EXISTS idx_admin_areas_name ON admin_areas (name);

-- ---------------------------------------------------------------------------
-- flood_zones: mapped hazard polygons. Authoritative when a point falls inside.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS flood_zones (
    id         BIGSERIAL PRIMARY KEY,
    name       VARCHAR(255),
    risk_level VARCHAR(16) NOT NULL CHECK (risk_level IN ('low', 'medium', 'high')),
    source     VARCHAR(64) NOT NULL,
    geom       geometry(MultiPolygon, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_flood_zones_geom ON flood_zones USING GIST (geom);

-- ---------------------------------------------------------------------------
-- waterways: rivers/streams/canals, for the "how close is water" signal.
-- Import single LineStrings with ST_Multi(geom).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS waterways (
    id     BIGSERIAL PRIMARY KEY,
    name   VARCHAR(255),
    kind   VARCHAR(32) NOT NULL,
    source VARCHAR(64) NOT NULL DEFAULT 'osm',
    geom   geometry(MultiLineString, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_waterways_geom ON waterways USING GIST (geom);

-- ---------------------------------------------------------------------------
-- elevation_points: sampled elevations, used as a cache / offline source.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS elevation_points (
    id          BIGSERIAL PRIMARY KEY,
    elevation_m DOUBLE PRECISION NOT NULL,
    source      VARCHAR(64) NOT NULL,
    geom        geometry(Point, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_elevation_points_geom ON elevation_points USING GIST (geom);

-- ---------------------------------------------------------------------------
-- hazard_cells: BNPB InaRISK hazard models, ingested from their ArcGIS
-- ImageServers into local geometry so lookups don't depend on BNPB being up.
--
--   python scripts/import_inarisk.py --bbox 106.6,-6.4,107.0,-6.0
--
-- One row per raster cell per hazard. `hazard_index` keeps the raw 0..1 value;
-- `risk_level` is BNPB's equal-thirds classification of it.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hazard_cells (
    id                BIGSERIAL PRIMARY KEY,
    hazard_type       VARCHAR(32) NOT NULL,
    hazard_index      DOUBLE PRECISION NOT NULL,
    risk_level        VARCHAR(16) NOT NULL CHECK (risk_level IN ('low', 'medium', 'high')),
    source            VARCHAR(64) NOT NULL DEFAULT 'BNPB InaRISK',
    resolution_meters INTEGER NOT NULL,
    cell_key          VARCHAR(64) NOT NULL,
    imported_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    geom              geometry(Polygon, 4326) NOT NULL,
    CONSTRAINT uq_hazard_cells_type_cell UNIQUE (hazard_type, cell_key)
);

CREATE INDEX IF NOT EXISTS idx_hazard_cells_geom ON hazard_cells USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_hazard_cells_type ON hazard_cells (hazard_type);

-- ---------------------------------------------------------------------------
-- hazard_coverage: which areas have been sampled, per hazard.
--
-- Without this, a missing hazard_cells row is ambiguous — "the model says no
-- hazard here" and "we never ingested this area" look identical. The first is
-- an answer; the second needs a live call to BNPB. `import_inarisk.py` records
-- one row per hazard per ingested bounding box.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hazard_coverage (
    id                BIGSERIAL PRIMARY KEY,
    hazard_type       VARCHAR(32) NOT NULL,
    resolution_meters INTEGER NOT NULL,
    source            VARCHAR(64) NOT NULL DEFAULT 'BNPB InaRISK',
    bbox_key          VARCHAR(96) NOT NULL,
    imported_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    geom              geometry(Polygon, 4326) NOT NULL,
    CONSTRAINT uq_hazard_coverage_type_bbox UNIQUE (hazard_type, bbox_key)
);

CREATE INDEX IF NOT EXISTS idx_hazard_coverage_geom ON hazard_coverage USING GIST (geom);

-- ---------------------------------------------------------------------------
-- Forward-compatibility: this file is re-runnable, and CREATE TABLE IF NOT
-- EXISTS won't add columns to a table you created with an earlier version.
-- These fill the gaps for an existing database.
-- ---------------------------------------------------------------------------
ALTER TABLE disaster_events
    ADD COLUMN IF NOT EXISTS scope VARCHAR(16) NOT NULL DEFAULT 'point';

-- Replaced rather than added: an existing database carries the two-value
-- constraint, which rejects 'provincial' outright.
ALTER TABLE disaster_events DROP CONSTRAINT IF EXISTS disaster_events_scope_check;

DO $$
BEGIN
    ALTER TABLE disaster_events
        ADD CONSTRAINT disaster_events_scope_check
        CHECK (scope IN ('point', 'regional', 'provincial'));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

ALTER TABLE disaster_events
    ADD COLUMN IF NOT EXISTS magnitude_scale        VARCHAR(16),
    ADD COLUMN IF NOT EXISTS magnitude_scale_source VARCHAR(32),
    ADD COLUMN IF NOT EXISTS depth_km               DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS intensity_mmi          DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS intensity_basis        VARCHAR(16),
    ADD COLUMN IF NOT EXISTS felt_reports           INTEGER,
    ADD COLUMN IF NOT EXISTS deaths                 INTEGER,
    ADD COLUMN IF NOT EXISTS missing                INTEGER,
    ADD COLUMN IF NOT EXISTS injured                INTEGER,
    ADD COLUMN IF NOT EXISTS displaced              INTEGER,
    ADD COLUMN IF NOT EXISTS houses_destroyed       INTEGER,
    ADD COLUMN IF NOT EXISTS houses_damaged         INTEGER,
    ADD COLUMN IF NOT EXISTS hazard_types           TEXT[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS area_name              VARCHAR(128);

-- Indexes for the columns added above. They live here, not beside the CREATE
-- TABLE, because on an existing database the table is left untouched and the
-- columns only appear at the ALTER — an index declared earlier would fail.
CREATE INDEX IF NOT EXISTS idx_disaster_events_hazards ON disaster_events USING GIN (hazard_types);
CREATE INDEX IF NOT EXISTS idx_disaster_events_area    ON disaster_events (area_name);

-- Existing rows predate the array, so seed it from the label they do have.
UPDATE disaster_events
   SET hazard_types = ARRAY[event_type]
 WHERE hazard_types = '{}' OR hazard_types IS NULL;

-- `magnitude_unit` was a free-form string that mixed USGS scale codes ("mb"),
-- whatever a custom feed happened to send, and NULL from GDACS — so the
-- magnitude column was not comparable between rows. Carry the old values over
-- as provenance, derive the normalised scale from them, then drop the column.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'disaster_events' AND column_name = 'magnitude_unit'
    ) THEN
        UPDATE disaster_events
           SET magnitude_scale_source = COALESCE(magnitude_scale_source, magnitude_unit)
         WHERE magnitude_unit IS NOT NULL;

        UPDATE disaster_events
           SET magnitude_scale = CASE lower(magnitude_scale_source)
                   WHEN 'mb'  THEN 'mb'  WHEN 'mblg' THEN 'mb'
                   WHEN 'mw'  THEN 'mw'  WHEN 'mww'  THEN 'mw'
                   WHEN 'mwc' THEN 'mw'  WHEN 'mwb'  THEN 'mw'
                   WHEN 'mwr' THEN 'mw'  WHEN 'mwp'  THEN 'mw'
                   WHEN 'ms'  THEN 'ms'  WHEN 'ms20' THEN 'ms'
                   WHEN 'ml'  THEN 'ml'  WHEN 'mlg'  THEN 'ml'
                   WHEN 'md'  THEN 'md'  WHEN 'm'    THEN 'm'
                   ELSE 'other'
               END
         WHERE magnitude_scale IS NULL AND magnitude_scale_source IS NOT NULL;

        ALTER TABLE disaster_events DROP COLUMN magnitude_unit;
    END IF;
END $$;

DO $$
BEGIN
    ALTER TABLE disaster_events
        ADD CONSTRAINT disaster_events_magnitude_scale_check
        CHECK (magnitude_scale IN ('mb','mw','ms','ml','md','m','other'));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE disaster_events
        ADD CONSTRAINT disaster_events_intensity_basis_check
        CHECK (intensity_basis IN ('modelled', 'reported'));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE disaster_events
        ADD CONSTRAINT disaster_events_intensity_mmi_check
        CHECK (intensity_mmi BETWEEN 1 AND 12);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;
