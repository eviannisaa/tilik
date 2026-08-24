#!/usr/bin/env python3
"""Load GDACS multi-hazard event history into the `disaster_events` table.

The live GDACS query returns only the ~100 most recent events for a country,
which reaches back about four years. The API does honour a date window though,
so walking year by year retrieves the full record — floods, volcanic eruptions,
wildfires, cyclones and droughts, each with a date and coordinates.

Earthquakes are deliberately excluded: USGS publishes real epicentres for those,
and including GDACS's quake stream would both duplicate them and crowd out
everything else inside the per-request record cap.

Usage:
    python scripts/import_gdacs.py                  # Indonesia, last 25 years
    python scripts/import_gdacs.py --years 10
    python scripts/import_gdacs.py --country "" --years 5   # worldwide
    python scripts/import_gdacs.py --dry-run

Rows upsert on `external_id`, so re-running to refresh is safe.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.core.config import get_settings  # noqa: E402
from api.core.errors import TilikError  # noqa: E402
from api.db.session import get_engine  # noqa: E402
from api.services import gdacs  # noqa: E402

UPSERT = text(
    """
    INSERT INTO disaster_events (
        external_id, event_type, title, occurred_at,
        magnitude, magnitude_unit, source, url, scope, geom
    )
    VALUES (
        :external_id, :event_type, :title, :occurred_at,
        NULL, NULL, :source, :url, :scope,
        ST_SetSRID(ST_MakePoint(:longitude, :latitude), 4326)
    )
    ON CONFLICT (external_id) DO UPDATE SET
        event_type  = EXCLUDED.event_type,
        scope       = EXCLUDED.scope,
        title       = EXCLUDED.title,
        occurred_at = EXCLUDED.occurred_at,
        url         = EXCLUDED.url,
        geom        = EXCLUDED.geom
    """
)


def to_row(feature: dict) -> dict | None:
    """Flatten a GDACS feature into an insertable row."""
    # Distance is irrelevant at ingest time, so any origin works.
    event = gdacs.to_event(feature, 0.0, 0.0)
    if event is None:
        return None

    coordinates = feature["geometry"]["coordinates"]
    title = event.title
    severity = event.severity
    if severity:
        title = f"{title} ({severity} alert)"

    return {
        "external_id": event.id,
        "event_type": event.type,
        "title": title,
        "occurred_at": (
            datetime.fromisoformat(event.occurred_at) if event.occurred_at else None
        ),
        "source": event.source,
        "url": event.url,
        # GDACS coordinates are centroids of affected regions, not epicentres.
        "scope": event.scope,
        "longitude": float(coordinates[0]),
        "latitude": float(coordinates[1]),
    }


async def main() -> int:
    settings = get_settings()

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--years", type=int, default=settings.disaster_years)
    parser.add_argument(
        "--country",
        default=settings.gdacs_country,
        help='Country name as GDACS spells it, or "" for worldwide',
    )
    parser.add_argument("--dry-run", action="store_true", help="Fetch and report, write nothing")
    args = parser.parse_args()

    this_year = datetime.now(UTC).year
    years = list(range(this_year - args.years + 1, this_year + 1))

    print(f"Country : {args.country or 'worldwide'}")
    print(f"Years   : {years[0]}–{years[-1]} ({len(years)} windows)")
    print(f"Types   : {', '.join(gdacs.EVENT_TYPES[code] for code in gdacs.REQUESTED_TYPES)}")

    engine = None
    if not args.dry_run:
        if not settings.database_url:
            print("\nDATABASE_URL is not set — nothing to import into.", file=sys.stderr)
            return 1
        engine = get_engine()
        if engine is None:
            print("\nCould not create a database engine.", file=sys.stderr)
            return 1

    seen: set[str] = set()
    stored = 0
    by_type: dict[str, int] = {}
    failures = 0

    for year in years:
        try:
            features = await gdacs.fetch_events(
                from_date=f"{year}-01-01",
                to_date=f"{year}-12-31",
                country=args.country or None,
            )
        except TilikError as exc:
            print(f"  {year}: failed ({exc})")
            failures += 1
            continue

        rows = []
        for feature in features:
            row = to_row(feature)
            # Windows overlap at year boundaries for multi-month events.
            if row is None or row["external_id"] in seen:
                continue
            seen.add(row["external_id"])
            rows.append(row)
            by_type[row["event_type"]] = by_type.get(row["event_type"], 0) + 1

        if rows and engine is not None:
            async with engine.begin() as connection:
                await connection.execute(UPSERT, rows)
        stored += len(rows)

        print(f"  {year}: {len(features):3} returned, {len(rows):3} new (total {stored})")
        # GDACS is a public good; don't hammer it.
        await asyncio.sleep(0.4)

    print(f"\n{'Would import' if args.dry_run else 'Imported'} {stored} event(s).")
    for event_type, count in sorted(by_type.items(), key=lambda item: -item[1]):
        print(f"  {event_type:20} {count}")

    if failures:
        print(f"\n{failures} year window(s) failed — re-run to fill the gaps.", file=sys.stderr)
    if not stored:
        print("\nNothing retrieved.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
