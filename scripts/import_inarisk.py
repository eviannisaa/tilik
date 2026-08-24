#!/usr/bin/env python3
"""Ingest BNPB InaRISK hazard models into the `hazard_cells` PostGIS table.

Why ingest instead of querying live: BNPB's ArcGIS server is slow (seconds per
layer) and frequently unavailable, which is a poor thing to sit in the critical
path of every location check. Sampling it once into PostGIS turns each lookup
into a local `ST_Intersects` and makes reports fast and reliable.

How it works: each InaRISK layer is an ImageServer holding a 0..1 hazard index
at 100 m resolution. The server's `getSamples` operation returns values for many
points in one request (capped at 1000), so this walks a grid over the requested
bounding box and stores each sampled cell as a square polygon.

Usage:
    # Greater Bandung, native 100 m resolution
    python scripts/import_inarisk.py --bbox 107.5,-7.0,107.8,-6.8

    # Coarser and faster, one hazard only
    python scripts/import_inarisk.py --bbox 106.6,-6.4,107.0,-6.0 \
        --cell-size 250 --hazards flood,landslide

    # See the cost before paying it
    python scripts/import_inarisk.py --bbox 106.6,-6.4,107.0,-6.0 --dry-run

Sample only the area you actually serve: Indonesia at 100 m is billions of
cells. Re-running an overlapping box is safe — rows upsert on (hazard, cell).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from pathlib import Path

import httpx
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.core.config import get_settings  # noqa: E402
from api.db.session import get_engine  # noqa: E402
from api.services.inarisk import HAZARD_LAYERS, classify_index  # noqa: E402

#: ArcGIS silently truncates `getSamples` to this many points per request.
MAX_SAMPLES_PER_REQUEST = 1000
#: Native resolution of the InaRISK rasters, in metres.
NATIVE_RESOLUTION_M = 100
#: Rough metres-per-degree of latitude; good enough for grid spacing.
METERS_PER_DEGREE = 111_320.0

COVERAGE_UPSERT = text(
    """
    INSERT INTO hazard_coverage (hazard_type, resolution_meters, source, bbox_key, geom)
    VALUES (
        :hazard_type, :resolution_meters, :source, :bbox_key,
        ST_MakeEnvelope(:west, :south, :east, :north, 4326)
    )
    ON CONFLICT (hazard_type, bbox_key) DO UPDATE SET
        resolution_meters = EXCLUDED.resolution_meters,
        geom              = EXCLUDED.geom,
        imported_at       = now()
    """
)

UPSERT = text(
    """
    INSERT INTO hazard_cells (
        hazard_type, hazard_index, risk_level, source,
        resolution_meters, cell_key, geom
    )
    VALUES (
        :hazard_type, :hazard_index, :risk_level, :source,
        :resolution_meters, :cell_key,
        ST_MakeEnvelope(:west, :south, :east, :north, 4326)
    )
    ON CONFLICT (hazard_type, cell_key) DO UPDATE SET
        hazard_index      = EXCLUDED.hazard_index,
        risk_level        = EXCLUDED.risk_level,
        resolution_meters = EXCLUDED.resolution_meters,
        geom              = EXCLUDED.geom,
        imported_at       = now()
    """
)


class Grid:
    """A regular lat/lng grid over a bounding box, anchored at (0, 0).

    Anchoring globally rather than to the box means the same ground always falls
    in the same cell, so `cell_key` stays stable across separate ingest runs and
    overlapping boxes upsert instead of duplicating.
    """

    def __init__(self, west: float, south: float, east: float, north: float, cell_size_m: int):
        self.cell_size_m = cell_size_m
        self.step_lat = cell_size_m / METERS_PER_DEGREE
        # Longitude degrees shrink towards the poles; size them at mid-latitude.
        mid_lat = (south + north) / 2
        shrink = max(0.05, math.cos(math.radians(mid_lat)))
        self.step_lng = cell_size_m / (METERS_PER_DEGREE * shrink)

        self.col_start = math.floor(west / self.step_lng)
        self.col_end = math.ceil(east / self.step_lng)
        self.row_start = math.floor(south / self.step_lat)
        self.row_end = math.ceil(north / self.step_lat)

    @property
    def cell_count(self) -> int:
        return (self.col_end - self.col_start) * (self.row_end - self.row_start)

    def cells(self):
        """Yield ``(cell_key, centre_lng, centre_lat, bounds)`` for every cell."""
        for col in range(self.col_start, self.col_end):
            for row in range(self.row_start, self.row_end):
                west = col * self.step_lng
                south = row * self.step_lat
                east = west + self.step_lng
                north = south + self.step_lat
                yield (
                    f"{col}:{row}",
                    (west + east) / 2,
                    (south + north) / 2,
                    (west, south, east, north),
                )


async def sample_layer(
    client: httpx.AsyncClient,
    base_url: str,
    layer: str,
    batch: list[tuple[str, float, float, tuple[float, float, float, float]]],
) -> tuple[dict[int, float], bool]:
    """Sample one layer at a batch of points.

    Returns ``({index: value}, ok)``. `ok` is False when the request itself
    failed, which must not be confused with a layer that answered and simply
    models nothing here — only the latter justifies recording coverage.
    """
    geometry = {
        "points": [[lng, lat] for _, lng, lat, _ in batch],
        "spatialReference": {"wkid": 4326},
    }

    for attempt in range(1, 4):
        try:
            response = await client.post(
                f"{base_url.rstrip('/')}/{layer}/ImageServer/getSamples",
                data={
                    "geometry": json.dumps(geometry, separators=(",", ":")),
                    "geometryType": "esriGeometryMultipoint",
                    "returnFirstValueOnly": "true",
                    "f": "json",
                },
            )
            payload = response.json()
        except Exception as exc:  # noqa: BLE001 - retry anything transient
            if attempt == 3:
                print(f"    ! {layer}: giving up after 3 attempts ({type(exc).__name__})")
                return {}, False
            await asyncio.sleep(2 * attempt)
            continue

        if "error" in payload:
            print(f"    ! {layer}: {payload['error'].get('message')}")
            return {}, False

        values: dict[int, float] = {}
        for sample in payload.get("samples", []):
            raw = sample.get("value")
            if raw in (None, "", "NoData"):
                continue
            try:
                values[int(sample["locationId"])] = float(raw)
            except (KeyError, TypeError, ValueError):
                continue
        return values, True

    return {}, False


def parse_bbox(raw: str) -> tuple[float, float, float, float]:
    parts = [float(part) for part in raw.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("--bbox needs west,south,east,north")

    west, south, east, north = parts
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise argparse.ArgumentTypeError(
            "--bbox must be west,south,east,north and within Earth's range"
        )
    return west, south, east, north


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--bbox", required=True, type=parse_bbox, help="west,south,east,north")
    parser.add_argument(
        "--cell-size",
        type=int,
        default=NATIVE_RESOLUTION_M,
        help=f"Grid cell size in metres (default {NATIVE_RESOLUTION_M}, the native resolution)",
    )
    parser.add_argument(
        "--hazards",
        default=",".join(HAZARD_LAYERS),
        help=f"Comma-separated subset of: {', '.join(HAZARD_LAYERS)}",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report the work, change nothing")
    args = parser.parse_args()

    hazards = [name.strip() for name in args.hazards.split(",") if name.strip()]
    unknown = [name for name in hazards if name not in HAZARD_LAYERS]
    if unknown:
        print(f"Unknown hazard(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"Available: {', '.join(HAZARD_LAYERS)}", file=sys.stderr)
        return 1

    west, south, east, north = args.bbox
    grid = Grid(west, south, east, north, args.cell_size)
    requests_per_hazard = math.ceil(grid.cell_count / MAX_SAMPLES_PER_REQUEST)

    print(f"Bounding box   : {west},{south},{east},{north}")
    print(f"Cell size      : {args.cell_size} m")
    print(f"Cells per layer: {grid.cell_count:,}")
    print(f"Hazards        : {', '.join(hazards)}")
    print(f"BNPB requests  : {requests_per_hazard * len(hazards):,}")

    if args.cell_size < NATIVE_RESOLUTION_M:
        print(
            f"\nNote: {args.cell_size} m is finer than InaRISK's {NATIVE_RESOLUTION_M} m source "
            "resolution, so neighbouring cells will repeat the same value."
        )

    if args.dry_run:
        print("\nDry run — nothing fetched or written.")
        return 0

    settings = get_settings()
    if not settings.database_url:
        print("\nDATABASE_URL is not set — nothing to import into.", file=sys.stderr)
        return 1

    engine = get_engine()
    if engine is None:
        print("\nCould not create a database engine.", file=sys.stderr)
        return 1

    all_cells = list(grid.cells())
    batches = [
        all_cells[start : start + MAX_SAMPLES_PER_REQUEST]
        for start in range(0, len(all_cells), MAX_SAMPLES_PER_REQUEST)
    ]

    totals: dict[str, int] = {}
    covered: list[str] = []
    incomplete: list[str] = []

    async with httpx.AsyncClient(
        timeout=120,
        headers={"Accept": "*/*", "User-Agent": settings.nominatim_user_agent},
    ) as client:
        for hazard in hazards:
            layer = HAZARD_LAYERS[hazard]
            stored = 0
            complete = True
            print(f"\n{hazard} ({layer})")

            for number, batch in enumerate(batches, start=1):
                values, ok = await sample_layer(
                    client, settings.inarisk_base_url, layer, batch
                )
                if not ok:
                    complete = False

                rows = []
                for position, value in values.items():
                    if position >= len(batch):
                        continue
                    cell_key, _, _, (cell_west, cell_south, cell_east, cell_north) = batch[position]
                    rows.append(
                        {
                            "hazard_type": hazard,
                            "hazard_index": value,
                            "risk_level": classify_index(value),
                            "source": "BNPB InaRISK",
                            "resolution_meters": args.cell_size,
                            "cell_key": cell_key,
                            "west": cell_west,
                            "south": cell_south,
                            "east": cell_east,
                            "north": cell_north,
                        }
                    )

                if rows:
                    async with engine.begin() as connection:
                        await connection.execute(UPSERT, rows)
                    stored += len(rows)

                print(
                    f"  batch {number}/{len(batches)}: "
                    f"{len(values)} sampled, {len(rows)} stored (running total {stored})"
                )
                # BNPB refuses connections when pushed; stay deliberately polite.
                await asyncio.sleep(0.5)

            totals[hazard] = stored
            if not complete:
                # Partial sampling must not claim coverage, or every point in
                # this box would answer "no hazard" on incomplete evidence.
                print(f"  ! {hazard}: some batches failed — coverage NOT recorded")
                incomplete.append(hazard)
                continue

            # Record that this box was fully sampled, so a later lookup can tell
            # "no hazard here" from "never ingested".
            async with engine.begin() as connection:
                await connection.execute(
                    COVERAGE_UPSERT,
                    {
                        "hazard_type": hazard,
                        "resolution_meters": args.cell_size,
                        "source": "BNPB InaRISK",
                        "bbox_key": f"{west:.5f},{south:.5f},{east:.5f},{north:.5f}",
                        "west": west,
                        "south": south,
                        "east": east,
                        "north": north,
                    },
                )
            covered.append(hazard)

    print("\nDone.")
    for hazard, count in totals.items():
        skipped = grid.cell_count - count
        print(f"  {hazard:12} {count:,} cells stored ({skipped:,} had no data)")

    if covered:
        print(
            f"\nCoverage recorded for {', '.join(covered)} — points inside this box "
            "now answer from PostGIS without calling BNPB."
        )
    if incomplete:
        print(
            f"Incomplete: {', '.join(incomplete)}. Re-run to finish; until then "
            "those hazards still fall back to the live service."
        )

    if not any(totals.values()):
        print("\nNothing was stored. BNPB may be down — try again later.", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
