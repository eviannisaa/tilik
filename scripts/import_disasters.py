#!/usr/bin/env python3
"""Load a BNPB/DIBI disaster export into the `disaster_events` PostGIS table.

DIBI (dibi.bnpb.go.id) has no public API — it's an authenticated Apache Superset
dashboard — so the supported path is to export from DIBI and import here. Once
loaded, reports read events from PostGIS first and stop depending on any
external service for disaster history.

Usage:
    python scripts/import_disasters.py path/to/dibi-export.csv

The CSV needs a latitude and a longitude column; everything else is optional.
Column names are matched case-insensitively against both English and Indonesian
variants, so a raw DIBI export usually works untouched. Rows are upserted on
`external_id`, so re-running an updated export is safe.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

# Allow `python scripts/import_disasters.py` from the repo root without an install.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.core.config import get_settings  # noqa: E402
from api.db.session import get_engine  # noqa: E402

#: Accepted column names per field, lowercased. First match wins.
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "latitude": ("latitude", "lat", "lintang", "y"),
    "longitude": ("longitude", "lon", "lng", "bujur", "x"),
    "event_type": ("type", "event_type", "jenis", "jenis_bencana", "kejadian"),
    "title": ("title", "judul", "lokasi", "kejadian", "nama_kejadian"),
    "occurred_at": ("date", "occurred_at", "tanggal", "tanggal_kejadian", "waktu"),
    "magnitude": ("magnitude", "magnitudo", "kekuatan"),
    "external_id": ("id", "external_id", "id_kejadian", "kode"),
}

DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d")


def pick(row: dict[str, Any], field: str) -> str | None:
    for alias in COLUMN_ALIASES[field]:
        for key, value in row.items():
            if key and key.strip().lower() == alias and str(value).strip():
                return str(value).strip()
    return None


def parse_date(raw: str | None) -> datetime | None:
    """Parse a DIBI date as UTC midnight.

    The column is a calendar date with no time or zone. A naive datetime would
    be reinterpreted using the database session's timezone, which shifts the
    date by a day either way — so anchor it explicitly.
    """
    if not raw:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw[: len(fmt) + 4], fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def parse_float(raw: str | None) -> float | None:
    if not raw:
        return None
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return None


def read_rows(path: Path) -> list[dict[str, Any]]:
    """Turn the export into rows ready for insertion, skipping unusable ones."""
    events: list[dict[str, Any]] = []
    skipped = 0

    with path.open(newline="", encoding="utf-8-sig") as handle:
        # DIBI exports vary between comma and semicolon delimiters.
        sample = handle.read(4096)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel

        for index, row in enumerate(csv.DictReader(handle, dialect=dialect), start=2):
            latitude = parse_float(pick(row, "latitude"))
            longitude = parse_float(pick(row, "longitude"))

            if latitude is None or longitude is None:
                skipped += 1
                continue
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                skipped += 1
                continue

            title = pick(row, "title") or "Recorded event"
            events.append(
                {
                    "external_id": pick(row, "external_id") or f"dibi-{index}",
                    "event_type": (pick(row, "event_type") or "disaster").lower(),
                    "title": title,
                    "occurred_at": parse_date(pick(row, "occurred_at")),
                    "magnitude": parse_float(pick(row, "magnitude")),
                    "magnitude_unit": None,
                    "source": "BNPB DIBI",
                    "url": None,
                    # DIBI locates events by regency, not by exact site.
                    "scope": "regional",
                    "latitude": latitude,
                    "longitude": longitude,
                }
            )

    if skipped:
        print(f"Skipped {skipped} row(s) without usable coordinates.", file=sys.stderr)
    return events


UPSERT = text(
    """
    INSERT INTO disaster_events (
        external_id, event_type, title, occurred_at,
        magnitude, magnitude_unit, source, url, scope, geom
    )
    VALUES (
        :external_id, :event_type, :title, :occurred_at,
        :magnitude, :magnitude_unit, :source, :url, :scope,
        ST_SetSRID(ST_MakePoint(:longitude, :latitude), 4326)
    )
    ON CONFLICT (external_id) DO UPDATE SET
        event_type = EXCLUDED.event_type,
        title      = EXCLUDED.title,
        occurred_at = EXCLUDED.occurred_at,
        magnitude  = EXCLUDED.magnitude,
        scope      = EXCLUDED.scope,
        geom       = EXCLUDED.geom
    """
)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path, help="DIBI/BNPB CSV export")
    args = parser.parse_args()

    if not args.csv_path.is_file():
        print(f"No such file: {args.csv_path}", file=sys.stderr)
        return 1

    if not get_settings().database_url:
        print("DATABASE_URL is not set — nothing to import into.", file=sys.stderr)
        return 1

    engine = get_engine()
    if engine is None:
        print("Could not create a database engine.", file=sys.stderr)
        return 1

    events = read_rows(args.csv_path)
    if not events:
        print("No importable rows found.", file=sys.stderr)
        return 1

    async with engine.begin() as connection:
        await connection.execute(UPSERT, events)

    print(f"Imported {len(events)} disaster event(s) into disaster_events.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
