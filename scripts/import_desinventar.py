#!/usr/bin/env python3
"""Load Indonesia's DesInventar disaster archive into `disaster_events`.

Why this exists
---------------
Tilik's disaster history is otherwise a seismic catalogue, and a seismic
catalogue answers the wrong question. Within 200 km of Serpong USGS holds ~700
events, a third of them 70 km or deeper in the subducting slab — felt by nobody,
listed as "disaster history" for a plot of land. Meanwhile the events that
actually hurt people there are floods, and USGS structurally cannot report one.

DesInventar (desinventar.net) publishes BNPB's own DIBI records — 33,000 events
back to 1815, every one with the counts that matter: deaths, injuries,
displacement, houses lost. DIBI itself has no public API; this export is the
supported way in.

Usage
-----
    curl -LO https://www.desinventar.net/DesInventar/download/DI_export_idn.zip
    python scripts/import_desinventar.py DI_export_idn.zip

Accepts the .zip as downloaded, or a directory it was extracted into.

Two limits worth knowing before you trust the output
----------------------------------------------------
* **Records stop in 2020.** The export is not maintained live. GDACS and the
  USGS catalogue still cover recent years; this fills in the deep history.
* **Locations are administrative, not surveyed.** Every `latitude`/`longitude`
  in the export is 0. Position comes from joining the record's area code to the
  boundary shapefiles shipped alongside it, then taking a representative point
  inside the largest ring. So a row means "this happened in this regency", never
  "this happened 300 m from your pin" — hence `scope = 'regional'`.
* **2.4% of rows are coarser still.** The bundled boundaries hold 428 regencies
  against today's ~514, because Indonesia kept splitting them. Where the child's
  name reveals its parent — Kota Tangerang Selatan from Tangerang, Pidie Jaya
  from Pidie — the parent's boundary is used, which rescued 1,356 rows. The rest
  (Sigi, whose parent Donggala is not in its name; Kalimantan Utara, created
  after the file) fall back to the province centroid, get
  `scope = 'provincial'`, and are counted in the run's output.
"""

from __future__ import annotations

import argparse
import asyncio
import struct
import sys
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO

from sqlalchemy import text

# Allow `python scripts/import_desinventar.py` from the repo root without an install.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.core.config import get_settings  # noqa: E402
from api.db.session import get_engine  # noqa: E402

#: DesInventar's Indonesian category → Tilik's event vocabulary, which is the
#: one GDACS and InaRISK already use so a row lines up with a hazard layer.
#:
#: ``GEMPA BUMI DAN TSUNAMI`` keeps a compound type of its own rather than
#: collapsing into either half. Folding it into ``tsunami`` looked harmless —
#: 27 records against 649 pure earthquakes — until those 27 turned out to be
#: Aceh 2004 and Palu 2018, carrying 170,791 of the archive's 188,621 combined
#: earthquake deaths. It would have moved 91% of them out of ``earthquake``.
#: It is also wrong about Palu specifically: most of those deaths came from
#: shaking and liquefaction at Petobo, Balaroa and Jono Oge, not from the wave.
#: Splitting the row in two instead would double-count every death.
EVENT_TYPES: dict[str, str] = {
    "BANJIR": "flood",
    "BANJIR DAN TANAH LONGSOR": "flood",
    "TANAH LONGSOR": "landslide",
    "PUTING BELIUNG": "extreme weather",
    "KEBAKARAN": "fire",
    "KEBAKARAN HUTAN DAN LAHAN": "wildfire",
    "KEKERINGAN": "drought",
    "GEMPA BUMI": "earthquake",
    "GEMPA BUMI DAN TSUNAMI": "earthquake and tsunami",
    "TSUNAMI": "tsunami",
    "LETUSAN GUNUNG API": "volcanic eruption",
    "GELOMBANG PASANG / ABRASI": "coastal erosion",
}

#: Display label → the atomic hazards behind it.
#:
#: Only the compound category needs an entry; everything else is its own single
#: hazard. This is what makes "has a tsunami ever reached here?" answerable for
#: Palu 2018 and Aceh 2004 while their death tolls stay on one row.
HAZARD_TYPES: dict[str, list[str]] = {
    "earthquake and tsunami": ["earthquake", "tsunami"],
}

#: Categories DIBI carries that say nothing about the ground under a plot of
#: land. Skipped deliberately, and counted so the run reports what it dropped
#: rather than quietly shrinking the archive.
SKIPPED_TYPES = frozenset(
    {
        "KECELAKAAN TRANSPORTASI",
        "KONFLIK / KERUSUHAN SOSIAL",
        "AKSI TEROR / SABOTASE",
        "EPIDEMI",
        "BANGUNAN ROBOH",
        "PERUBAHAN IKLIM",
        "LAINNYA",
    }
)

#: Impact column → DesInventar field and its companion availability flag.
#:
#: The flag is what makes a zero readable. DesInventar writes `hay_x = -1` when
#: it holds a real figure, `1` for a reported zero, and `0` when nothing was
#: recorded — and `damnificados` never uses `1` at all, so 29,208 of 33,010
#: events have a displacement count of 0 that means "unknown". Storing those as
#: zero would invent an all-clear; they become NULL.
IMPACT_FIELDS: dict[str, tuple[str, str]] = {
    "deaths": ("muertos", "hay_muertos"),
    "missing": ("desaparece", "hay_deasparece"),  # sic — misspelt in the export
    "injured": ("heridos", "hay_heridos"),
    "displaced": ("evacuados", "hay_evacuados"),
    "houses_destroyed": ("vivdest", "hay_vivdest"),
    "houses_damaged": ("vivafec", "hay_vivafec"),
}

#: Admin level → (record code field, shapefile stem, DBF code field,
#: record name field, DBF name field). Most specific first: a district centroid
#: beats a province centroid by a wide margin, and Indonesian provinces are far
#: too big to be a useful location.
ADMIN_LEVELS: tuple[tuple[str, str, str, str, str], ...] = (
    ("level2", "id2", "lev2_cod", "name2", "lev2_name"),
    ("level1", "id1", "KODE_KAB", "name1", "KAB_KOTA"),
    ("level0", "id0", "LEV0", "name0", "LEV0_NAME"),
)

#: Which boundary a row's position actually came from, as a `scope` value.
#:
#: The province fallback needs its own scope because it is not a location. The
#: bundled shapefile holds 428 regencies; Indonesia now has around 514, because
#: it kept splitting them — *pemekaran*. Sigi (split from Donggala in 2008),
#: Pidie Jaya, Kota Serang and Kota Tangerang Selatan, among others, have no
#: polygon here, so their events land on the province centroid instead.
#:
#: That misplaces 2,133 rows by up to ~130 km, and the direction of the error
#: matters: Palu's 289 deaths in Sigi get placed in empty mountains 130 km
#: east, so they would surface for a pin near that arbitrary point and be
#: missing from Sigi itself. Marked rather than dropped, since `assessment.py`
#: already restricts its "significant events nearby" test to `point` and the UI
#: can say plainly how coarse the position is.
SCOPE_BY_LEVEL: dict[str, str] = {
    "id2": "regional",
    "id1": "regional",
    # Matched to the parent regency by name rather than by its own code. Still a
    # real regency boundary, so still `regional`.
    "id1-parent": "regional",
    "id0": "provincial",
}

BATCH_SIZE = 2_000


# --------------------------------------------------------------------------- #
# Shapefile reading
#
# Only two things are needed from the boundaries — a code and a point inside the
# polygon — so this reads the format directly rather than adding a GIS
# dependency for one import script.
# --------------------------------------------------------------------------- #


def read_dbf(handle: BinaryIO) -> list[dict[str, str]]:
    """Every record of a dBase III table, as strings."""
    data = handle.read()
    record_count = struct.unpack("<I", data[4:8])[0]
    header_length = struct.unpack("<H", data[8:10])[0]
    record_length = struct.unpack("<H", data[10:12])[0]

    fields: list[tuple[str, int]] = []
    offset = 32
    while data[offset] != 0x0D:
        descriptor = data[offset : offset + 32]
        name = descriptor[0:11].split(b"\0")[0].decode("latin-1")
        fields.append((name, descriptor[16]))
        offset += 32

    rows: list[dict[str, str]] = []
    position = header_length
    for _ in range(record_count):
        record = data[position : position + record_length]
        position += record_length
        if not record:
            break
        row: dict[str, str] = {}
        cursor = 1  # byte 0 is the deletion flag
        for name, width in fields:
            row[name] = record[cursor : cursor + width].decode("latin-1").strip()
            cursor += width
        rows.append(row)
    return rows


def _ring_centroid(points: list[tuple[float, float]]) -> tuple[float, float, float]:
    """Area-weighted centroid of one ring, as ``(x, y, abs_area)``."""
    area = 0.0
    cx = 0.0
    cy = 0.0
    for index in range(len(points) - 1):
        x0, y0 = points[index]
        x1, y1 = points[index + 1]
        cross = x0 * y1 - x1 * y0
        area += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross

    if area == 0:
        # Degenerate ring (a line, or a repeated point): fall back to the mean.
        count = max(len(points), 1)
        return (
            sum(x for x, _ in points) / count,
            sum(y for _, y in points) / count,
            0.0,
        )

    area *= 0.5
    return cx / (6.0 * area), cy / (6.0 * area), abs(area)


def read_shp_rings(handle: BinaryIO) -> Iterator[list[list[tuple[float, float]]] | None]:
    """The raw rings of each polygon record, in file order.

    Parsed once and handed out whole, because two different things are built
    from them: a representative point for placing an event, and the boundary
    itself for testing whether an area comes within a radius.
    """
    data = handle.read()
    position = 100  # skip the file header
    end = len(data)

    while position + 8 <= end:
        content_length = struct.unpack(">i", data[position + 4 : position + 8])[0] * 2
        body = position + 8
        position = body + content_length

        shape_type = struct.unpack("<i", data[body : body + 4])[0]
        if shape_type not in (5, 15, 25):  # 0 is a null shape; others aren't polygons
            yield None
            continue

        part_count = struct.unpack("<i", data[body + 36 : body + 40])[0]
        point_count = struct.unpack("<i", data[body + 40 : body + 44])[0]
        parts_at = body + 44
        points_at = parts_at + 4 * part_count

        starts = list(struct.unpack(f"<{part_count}i", data[parts_at:points_at]))
        starts.append(point_count)

        rings: list[list[tuple[float, float]]] = []
        for part in range(part_count):
            first, last = starts[part], starts[part + 1]
            chunk = data[points_at + 16 * first : points_at + 16 * last]
            flat = struct.unpack(f"<{2 * (last - first)}d", chunk)
            # Interleaved x,y pairs — strict because an odd count would mean the
            # record length disagreed with the point count, i.e. a corrupt file.
            ring = list(zip(flat[0::2], flat[1::2], strict=True))
            if len(ring) >= 3:
                rings.append(ring)

        yield rings or None


def representative_point(
    rings: list[list[tuple[float, float]]],
) -> tuple[float, float, float] | None:
    """A point inside the largest ring, as ``(lat, lon, area)``.

    The largest ring, not all of them averaged: many Indonesian regencies are
    archipelagos, and averaging their islands puts the point in open water.
    """
    best: tuple[float, float, float] | None = None
    for ring in rings:
        candidate = _ring_centroid(ring)
        if best is None or candidate[2] > best[2]:
            best = candidate
    return (best[1], best[0], best[2]) if best else None


def multipolygon_wkt(rings: list[list[tuple[float, float]]]) -> str | None:
    """The rings as a MULTIPOLYGON, one polygon per ring.

    Holes are not separated out. A shapefile marks them only by winding order,
    and treating an enclave as solid can at worst include an area a hair early —
    against the alternative of hand-rolling orientation logic for a boundary
    file used only to answer "does this area come within N km". Enclaves are
    rare in Indonesian regency data. `ST_MakeValid` on insert repairs whatever
    self-intersects.

    Coordinates are trimmed to five decimals, roughly a metre, which keeps the
    table small without mattering at this scale.
    """
    polygons = []
    for ring in rings:
        closed = ring if ring[0] == ring[-1] else [*ring, ring[0]]
        if len(closed) < 4:
            continue
        coords = ", ".join(f"{x:.5f} {y:.5f}" for x, y in closed)
        polygons.append(f"(({coords}))")
    return f"MULTIPOLYGON({', '.join(polygons)})" if polygons else None


class Archive:
    """Reads members from either the downloaded .zip or an extracted directory."""

    def __init__(self, path: Path) -> None:
        self._zip = zipfile.ZipFile(path) if path.is_file() else None
        self._dir = None if self._zip else path
        if self._zip is not None:
            self._names = {Path(n).name: n for n in self._zip.namelist()}

    def open(self, name: str) -> BinaryIO:
        if self._zip is not None:
            member = self._names.get(name)
            if member is None:
                raise FileNotFoundError(name)
            return self._zip.open(member)
        candidate = self._dir / name  # type: ignore[operator]
        if not candidate.is_file():
            raise FileNotFoundError(str(candidate))
        return candidate.open("rb")

    def close(self) -> None:
        if self._zip is not None:
            self._zip.close()


#: Provinces the archive and the boundaries spell differently.
#:
#: Only three names disagree out of 34. Two are official renamings the shapefile
#: predates; the third, Kalimantan Utara, was created in 2012 and has no
#: boundary here at all, so its rows can only ever be province-level.
PROVINCE_ALIASES: dict[str, str] = {
    "ACEH": "NANGGROE ACEH DARUSSALAM",
    "DI YOGYAKARTA": "DAERAH ISTIMEWA YOGYAKARTA",
}


def _province_key(name: str) -> str:
    """The province name as the boundary file spells it."""
    text = _normalise_area(name)
    return PROVINCE_ALIASES.get(text, text)


def _normalise_area(name: str) -> str:
    """Collapse an area name for comparison, without discarding its type.

    ``KOTA`` and ``KAB.`` must survive: the boundaries hold ``BOGOR`` and
    ``KOTA BOGOR`` as separate areas, so stripping the prefix would silently
    place a city's events in the surrounding regency. Only spacing, case and
    the ``KABUPATEN``/``KAB.`` spelling are unified.
    """
    text = " ".join(name.upper().split())
    if text.startswith("KABUPATEN "):
        text = "KAB. " + text[len("KABUPATEN ") :]
    return text


def load_boundaries(
    archive: Archive, stem: str, code_field: str, name_field: str
) -> tuple[
    dict[str, tuple[float, float]],
    dict[str, tuple[float, float]],
    dict[str, list[str]],
    dict[str, str],
]:
    """One admin level, as ``(by_code, by_name, polygons_by_display_name)``.

    The points place an event; the polygons let a query ask whether an area
    reaches within a radius, rather than whether its centre happens to.
    ``polygons_by_display_name`` is keyed the way :func:`_place` renders a name,
    so it lines up with ``disaster_events.area_name``.
    """
    with archive.open(f"{stem}.dbf") as handle:
        rows = read_dbf(handle)
    with archive.open(f"{stem}.shp") as handle:
        ring_sets = list(read_shp_rings(handle))

    # One code can appear on several records — id2 holds 8,745 rows for 5,417
    # districts — so keep the largest polygon rather than whichever came first,
    # which would sometimes pick an offshore islet over the district proper.
    by_code: dict[str, tuple[float, float, float]] = {}
    by_name: dict[str, tuple[float, float, float]] = {}
    polygons: dict[str, list[str]] = {}
    # Code → the boundary's display name, so a row positioned by code can still
    # say which boundary defined it.
    name_by_code: dict[str, str] = {}

    for row, rings in zip(rows, ring_sets, strict=False):
        if rings is None:
            continue
        point = representative_point(rings)
        if point is None:
            continue
        latitude, longitude, area = point
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            continue

        raw_name = (row.get(name_field) or "").strip()

        # Every record for an area contributes its rings, so an archipelago
        # keeps all of its islands rather than only the biggest one.
        if raw_name:
            wkt = multipolygon_wkt(rings)
            if wkt:
                polygons.setdefault(_display_area(raw_name), []).append(wkt)

        code = (row.get(code_field) or "").strip().lstrip("0")
        if code:
            current = by_code.get(code)
            if current is None or area > current[2]:
                by_code[code] = (latitude, longitude, area)
            if raw_name:
                name_by_code.setdefault(code, _display_area(raw_name))

        # Keyed by province as well as name. Without it, name matching crosses
        # islands: "BATU BARA" in North Sumatra matched Kota "BATU" in East
        # Java, 1,500 km away, and "PADANG LAWAS" matched Kota Padang in West
        # Sumatra. A parent regency is always in its child's own province.
        name = _normalise_area(row.get(name_field) or "")
        province = _normalise_area(row.get("PROPINSI") or row.get("LEV0_NAME") or "")
        if name:
            key = f"{province}|{name}"
            current = by_name.get(key)
            if current is None or area > current[2]:
                by_name[key] = (latitude, longitude, area)

    return (
        {key: (lat, lng) for key, (lat, lng, _) in by_code.items()},
        {key: (lat, lng) for key, (lat, lng, _) in by_name.items()},
        polygons,
        name_by_code,
    )


def resolve_parent(
    name: str, province: str, by_name: dict[str, tuple[float, float]]
) -> str | None:
    """The boundary a split-off area belongs inside, matched by name.

    Indonesia kept subdividing its regencies — *pemekaran* — and these
    boundaries predate much of it: 428 areas against today's ~514. A regency
    created after the shapefile has no polygon, and falling all the way back to
    the province centroid moved 2,133 rows by up to 130 km, far enough that
    Serpong's own five recorded floods dropped out of a 50 km search while
    neighbouring Jakarta's showed up as if they were local.

    Indonesian naming makes the parent recoverable: a new area is almost always
    its parent's name plus a qualifier — Kota Tangerang Selatan from Tangerang,
    Pidie Jaya from Pidie, Mamuju Tengah from Mamuju. So drop trailing words
    until a real boundary matches.

    Exact matches are handled by the caller *before* this runs, which is what
    keeps ``KOTA BOGOR`` off ``BOGOR``. Matching is on whole words, so
    ``PEMALANG`` never resolves to ``MALANG``.

    Confined to the record's own province, which is what stops the matches that
    were plainly wrong: "BATU BARA" (North Sumatra) resolving to Kota "BATU" in
    East Java, and "PADANG LAWAS" (North Sumatra) to Kota Padang in West
    Sumatra. A regency's parent is never on another island.
    """
    prefix = _province_key(province)
    words = _normalise_area(name).split()
    # Drop the area-type prefix only here, where an exact match has already
    # failed: a child city's parent is the regency of the same stem.
    if words and words[0] in {"KOTA", "KAB."}:
        words = words[1:]
        # The stripped name itself first: a city absent from the boundaries is
        # normally enclosed by the regency of the same stem, so "KOTA TANGERANG"
        # belongs with "TANGERANG". Cities the file *does* hold — Kota Bogor,
        # Kota Bekasi — were already matched exactly by the caller and never
        # reach here, which is what stops them collapsing onto their regency.
        for candidate in (" ".join(words), "KAB. " + " ".join(words)):
            if f"{prefix}|{candidate}" in by_name:
                return candidate

    while len(words) > 1:
        words = words[:-1]
        for candidate in (" ".join(words), "KAB. " + " ".join(words)):
            if f"{prefix}|{candidate}" in by_name:
                return candidate
    return None


# --------------------------------------------------------------------------- #
# Event records
# --------------------------------------------------------------------------- #


def _int(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return int(float(raw))
    except ValueError:
        return None


def _impact(record: dict[str, str]) -> dict[str, int | None]:
    """Read the impact counts, honouring DesInventar's availability flags."""
    out: dict[str, int | None] = {}
    for column, (value_field, flag_field) in IMPACT_FIELDS.items():
        flag = (record.get(flag_field) or "").strip()
        value = _int(record.get(value_field))
        if flag == "-1":
            out[column] = value if value is not None else None
        elif flag == "1":
            out[column] = 0
        else:  # "0", blank, anything unexpected: not recorded
            out[column] = None
    return out


def _occurred_at(record: dict[str, str]) -> datetime | None:
    """Assemble the event date, tolerating the missing months and days DIBI has."""
    year = _int(record.get("fechano"))
    if not year or not (1500 <= year <= 2100):
        return None
    month = _int(record.get("fechames")) or 1
    day = _int(record.get("fechadia")) or 1
    try:
        return datetime(year, max(1, min(12, month)), max(1, min(31, day)), tzinfo=UTC)
    except ValueError:
        # e.g. 31 February — keep the month, which is the part that matters.
        return datetime(year, max(1, min(12, month)), 1, tzinfo=UTC)


def _display_area(name: str) -> str:
    """An area name as the report shows it: "KOTA BOGOR" → "Kota Bogor".

    Shared by the event rows and the boundary table so their keys cannot drift.
    A row's ``area_name`` is what joins it to its polygon, and a casing
    difference would silently leave the area with no boundary to test against.
    Short words stay upper — Indonesian names are full of DKI, NTT, Kab.
    """
    return " ".join(
        word.capitalize() if len(word) > 3 else word.upper() for word in name.split()
    )


def _place(record: dict[str, str]) -> str:
    """The most specific area name the record carries, nicely cased."""
    for field in ("name2", "name1", "name0"):
        name = (record.get(field) or "").strip()
        if name:
            return _display_area(name)
    return "Indonesia"


def _magnitude(record: dict[str, str]) -> tuple[float | None, str | None, str | None]:
    """Magnitude, when the free-text field holds a usable number.

    In practice it never does: `magnitud2` is empty in all 33,010 records of the
    August 2026 export, Palu 2018 and Aceh 2004 included. DIBI is a loss
    database, not a seismic one — it counts what happened to people and leaves
    the instrument reading to BMKG. So every imported row has a NULL magnitude,
    and the disaster section shows these events by their impact instead.

    Kept, and tested, because the column exists and a later export may fill it.
    If it ever does, DIBI still names no scale, which is the unlabelled ``m``
    case — the same footing as a BMKG bulletin and explicitly not comparable
    with a USGS ``mb`` value.
    """
    raw = (record.get("magnitud2") or "").strip().replace(",", ".")
    if not raw:
        return None, None, None
    try:
        value = float(raw)
    except ValueError:
        return None, None, None
    if not (0 < value <= 10):
        return None, None, None
    return value, "m", "unlabelled (DIBI)"


def _resolve_location(
    record: dict[str, str],
    boundaries: dict[str, tuple[dict[str, tuple[float, float]], dict[str, tuple[float, float]]]],
) -> tuple[tuple[float, float] | None, str, str | None]:
    """Best available position for one record, as ``(point, level, matched_as)``.

    Ordered by how much it actually pins down:

    1. the record's own area code, most specific level first;
    2. its area *name*, exactly — for codes the shapefile numbers differently;
    3. its parent regency by name, for areas created after the shapefile;
    4. the province, which is a last resort and not really a location.

    Steps 2 and 3 are what keep a regency's own history in its own regency.
    The province is reached only after both have failed — trying its code inside
    the same loop as the finer levels would satisfy almost every record and the
    name fallback would never run at all.
    """
    for field, stem, _code_field, _name_field, _dbf_name in ADMIN_LEVELS:
        if stem == "id0":
            continue  # last resort, handled below
        by_code, _, name_by_code = boundaries[stem]
        code = (record.get(field) or "").strip().lstrip("0")
        if code:
            hit = by_code.get(code)
            if hit:
                return hit, stem, name_by_code.get(code)

    # The regency is the level worth rescuing: provinces are too coarse to be
    # useful, and the district level is almost empty in this export.
    _, by_name, _ = boundaries["id1"]
    raw = record.get("name1") or ""
    province = _province_key(record.get("name0") or "")
    if raw:
        exact = _normalise_area(raw)
        if f"{province}|{exact}" in by_name:
            return by_name[f"{province}|{exact}"], "id1", exact
        parent = resolve_parent(raw, province, by_name)
        if parent:
            return by_name[f"{province}|{parent}"], "id1-parent", parent

    by_code0, _, name_by_code0 = boundaries["id0"]
    province = (record.get("level0") or "").strip().lstrip("0")
    if province and province in by_code0:
        return by_code0[province], "id0", name_by_code0.get(province)

    return None, "", None


def read_events(
    archive: Archive, boundaries: dict[str, tuple[Any, Any, Any]]
) -> tuple[
    list[dict[str, Any]],
    dict[str, int],
    dict[str, str],
    dict[tuple[str, str], tuple[str, str]],
]:
    """Stream the export into insertable rows.

    The XML is ~340 MB uncompressed, so it is parsed incrementally and each
    record is cleared once read.
    """
    events: list[dict[str, Any]] = []
    parents: dict[str, str] = {}
    # (area_name, scope) -> (shapefile stem, boundary display name). Records
    # positioned by a parent regency, or by a province, sit under a boundary
    # with a different name from their own — so the boundary each area actually
    # used is remembered here and stored under that area's name. Without it the
    # polygon join missed 18% of rows and they silently fell back to centroids.
    used: dict[tuple[str, str], tuple[str, str]] = {}
    tally = {
        "skipped_type": 0,
        "unknown_type": 0,
        "no_location": 0,
        "no_date": 0,
        "provincial": 0,
    }

    with archive.open("DI_export_idn.xml") as handle:
        for _, element in ET.iterparse(handle, events=("end",)):
            if element.tag != "TR":
                continue
            record = {child.tag: (child.text or "").strip() for child in element}
            # The file starts with lookup tables that share the <TR> tag; only
            # event records carry impact columns.
            if "muertos" not in record:
                element.clear()
                continue

            category = (record.get("evento") or "").strip().upper()
            event_type = EVENT_TYPES.get(category)
            if event_type is None:
                tally["skipped_type" if category in SKIPPED_TYPES else "unknown_type"] += 1
                element.clear()
                continue

            location, resolved, matched_as = _resolve_location(record, boundaries)
            if location is None:
                tally["no_location"] += 1
                element.clear()
                continue

            scope = SCOPE_BY_LEVEL[resolved]
            if scope == "provincial":
                tally["provincial"] += 1
            area = _place(record)
            if matched_as:
                used[(area, scope)] = (
                    "id0" if resolved == "id0" else "id1",
                    matched_as,
                )
            if resolved == "id1-parent" and matched_as:
                # Recorded per distinct area, not per row, so the report stays
                # short enough to actually read and audit.
                parents[_normalise_area(record.get("name1") or "")] = matched_as

            occurred_at = _occurred_at(record)
            if occurred_at is None:
                tally["no_date"] += 1

            magnitude, scale, scale_source = _magnitude(record)
            identity = (record.get("uu_id") or record.get("serial") or "").strip()

            events.append(
                {
                    "external_id": f"desinventar-{identity or len(events)}",
                    "event_type": event_type,
                    "hazard_types": HAZARD_TYPES.get(event_type, [event_type]),
                    "area_name": _place(record),
                    # The place alone. DIBI carries no event title, so this one
                    # is synthesised — and prefixing it with the hazard printed
                    # the type twice in every row, once as the headline and
                    # again in the line beneath it.
                    "title": _place(record),
                    "occurred_at": occurred_at,
                    "magnitude": magnitude,
                    "magnitude_scale": scale,
                    "magnitude_scale_source": scale_source,
                    "depth_km": None,
                    "intensity_mmi": None,
                    "intensity_basis": None,
                    "felt_reports": None,
                    "source": "BNPB DIBI (DesInventar)",
                    "url": None,
                    # Located by administrative area, never surveyed.
                    "scope": scope,
                    "latitude": location[0],
                    "longitude": location[1],
                    **_impact(record),
                }
            )
            element.clear()

    return events, tally, parents, used


UPSERT = text(
    """
    INSERT INTO disaster_events (
        external_id, event_type, hazard_types, area_name, title, occurred_at,
        magnitude, magnitude_scale, magnitude_scale_source,
        depth_km, intensity_mmi, intensity_basis, felt_reports,
        deaths, missing, injured, displaced, houses_destroyed, houses_damaged,
        source, url, scope, geom
    )
    VALUES (
        :external_id, :event_type, :hazard_types, :area_name, :title, :occurred_at,
        :magnitude, :magnitude_scale, :magnitude_scale_source,
        :depth_km, :intensity_mmi, :intensity_basis, :felt_reports,
        :deaths, :missing, :injured, :displaced, :houses_destroyed, :houses_damaged,
        :source, :url, :scope,
        ST_SetSRID(ST_MakePoint(:longitude, :latitude), 4326)
    )
    ON CONFLICT (external_id) DO UPDATE SET
        event_type       = EXCLUDED.event_type,
        hazard_types     = EXCLUDED.hazard_types,
        area_name        = EXCLUDED.area_name,
        title            = EXCLUDED.title,
        occurred_at      = EXCLUDED.occurred_at,
        magnitude        = EXCLUDED.magnitude,
        magnitude_scale  = EXCLUDED.magnitude_scale,
        magnitude_scale_source = EXCLUDED.magnitude_scale_source,
        deaths           = EXCLUDED.deaths,
        missing          = EXCLUDED.missing,
        injured          = EXCLUDED.injured,
        displaced        = EXCLUDED.displaced,
        houses_destroyed = EXCLUDED.houses_destroyed,
        houses_damaged   = EXCLUDED.houses_damaged,
        scope            = EXCLUDED.scope,
        geom             = EXCLUDED.geom
    """
)


AREA_UPSERT = text(
    """
    INSERT INTO admin_areas (name, level, source, geom)
    VALUES (
        :name, :level, :source,
        -- ST_MakeValid repairs the self-intersections that come from treating
        -- every ring as its own polygon, but it answers with a
        -- GeometryCollection whenever the repair leaves stray lines or points
        -- behind — which the column rejects. ST_CollectionExtract(..., 3) keeps
        -- just the polygonal parts and always yields a MultiPolygon.
        ST_CollectionExtract(ST_MakeValid(ST_GeomFromText(:wkt, 4326)), 3)
    )
    ON CONFLICT (name, level) DO UPDATE SET
        geom = EXCLUDED.geom,
        source = EXCLUDED.source
    """
)


def summarise(
    events: list[dict[str, Any]], tally: dict[str, int], parents: dict[str, str]
) -> None:
    """Report what was read, including what was left out."""
    by_type: dict[str, int] = {}
    for event in events:
        by_type[event["event_type"]] = by_type.get(event["event_type"], 0) + 1

    print(f"Read {len(events)} event(s):")
    for kind, count in sorted(by_type.items(), key=lambda item: -item[1]):
        print(f"  {kind:20} {count:6}")

    years = [event["occurred_at"].year for event in events if event["occurred_at"]]
    if years:
        print(f"Covering {min(years)}–{max(years)}.")

    deaths = sum(event["deaths"] or 0 for event in events)
    print(f"Recorded deaths across the archive: {deaths:,}")

    if parents:
        # Name matching is a heuristic, so every match it made is printed: these
        # are the areas created after the boundaries were drawn, placed in the
        # regency they were split from. Read them — a wrong one is a wrong map.
        print(f"\nMatched {len(parents)} area(s) to the regency they split from:")
        for child, parent in sorted(parents.items()):
            print(f"  {child:34} -> {parent}")

    provincial = tally["provincial"]
    if provincial:
        print(
            f"Position: {len(events) - provincial} located to a regency, "
            f"{provincial} only to a province."
        )
        print(
            "  The bundled boundaries predate Indonesia's regency splits, so "
            "those rows carry scope='provincial' and their distances are not "
            "meaningful. These are the areas whose parent could not be read "
            "from their name, such as Sigi (split from Donggala)."
        )

    if tally["skipped_type"]:
        print(
            f"Skipped {tally['skipped_type']} non-ground event(s) "
            "(transport, conflict, epidemic).",
            file=sys.stderr,
        )
    for key, message in (
        ("unknown_type", "unrecognised category"),
        ("no_location", "no resolvable area code"),
        ("no_date", "no usable date (kept, date left blank)"),
    ):
        if tally[key]:
            print(f"Note: {tally[key]} record(s) with {message}.", file=sys.stderr)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        type=Path,
        help="DI_export_idn.zip, or a directory it was extracted into",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and report without touching the database.",
    )
    args = parser.parse_args()

    if not args.path.exists():
        print(f"No such path: {args.path}", file=sys.stderr)
        return 1

    engine = None
    if not args.dry_run:
        if not get_settings().database_url:
            print("DATABASE_URL is not set — nothing to import into.", file=sys.stderr)
            return 1
        engine = get_engine()
        if engine is None:
            print("Could not create a database engine.", file=sys.stderr)
            return 1

    archive = Archive(args.path)
    try:
        loaded = {
            stem: load_boundaries(archive, stem, code_field, name_field)
            for _, stem, code_field, _record_name, name_field in ADMIN_LEVELS
        }
        # The resolver needs codes, names and the code→name map; the boundary
        # writer needs the polygons.
        boundaries = {
            stem: (codes, names, name_by_code)
            for stem, (codes, names, _shapes, name_by_code) in loaded.items()
        }
        polygons = {stem: shapes for stem, (_c, _n, shapes, _nbc) in loaded.items()}
        for _, stem, _c, _r, _n in ADMIN_LEVELS:
            by_code, by_name, _ = boundaries[stem]
            print(f"Loaded {len(by_code)} boundaries from {stem}.shp ({len(by_name)} named)")

        events, tally, parents, used = read_events(archive, boundaries)
    except FileNotFoundError as exc:
        print(f"Archive is missing {exc} — is this the DesInventar export?", file=sys.stderr)
        return 1
    finally:
        archive.close()

    if not events:
        print("No importable rows found.", file=sys.stderr)
        return 1

    summarise(events, tally, parents)

    if args.dry_run or engine is None:
        print("Dry run — nothing written.")
        return 0

    for start in range(0, len(events), BATCH_SIZE):
        batch = events[start : start + BATCH_SIZE]
        async with engine.begin() as connection:
            await connection.execute(UPSERT, batch)
        print(f"  wrote {min(start + BATCH_SIZE, len(events))}/{len(events)}", end="\r")

    print(f"\nImported {len(events)} disaster event(s) into disaster_events.")

    # Boundaries, so a query can ask whether an area reaches within a radius
    # rather than whether its centre happens to. Regency level and province
    # level only: the district file is barely referenced by the event records.
    # Stored under the *area's own name*, not the boundary's. A record for Kota
    # Tangerang Selatan is positioned by Tangerang's polygon, and one for Sigi by
    # its province's; keying on the boundary's name left those rows unable to
    # find their geometry — 18% of the archive, silently back on centroids.
    rows = []
    for (area, scope), (stem, boundary) in sorted(used.items()):
        # Regency boundaries only. A province polygon would make its records
        # match almost any pin inside it: with Banten's outline, events in Kota
        # Serang read as 0 km from a pin in Serpong, and Pangandaran — 250 km
        # away in West Java — read as 6 km because that province's edge is that
        # close. A province is not a location, so those rows keep their centroid
        # and stay conservatively far.
        if scope != "regional" or stem != "id1":
            continue
        # `resolve_parent` answers in normalised upper case while the polygons
        # are keyed the way a name is displayed, so the two have to be brought
        # to the same form — a silent miss here drops the area back to its
        # centroid.
        shapes = polygons[stem].get(_display_area(boundary))
        if not shapes:
            continue
        rows.append(
            {
                "name": area,
                "level": "province" if scope == "provincial" else "regency",
                "source": "DesInventar boundaries",
                # An area's rings can span several shapefile rows, so they are
                # merged into one multipolygon.
                "wkt": "MULTIPOLYGON("
                + ", ".join(wkt[len("MULTIPOLYGON(") : -1] for wkt in shapes)
                + ")",
            }
        )

    stored_areas = 0
    for start in range(0, len(rows), 100):
        async with engine.begin() as connection:
            await connection.execute(AREA_UPSERT, rows[start : start + 100])
        stored_areas += len(rows[start : start + 100])
        print(f"  boundaries: {stored_areas}", end="\r")

    print(f"\nStored {stored_areas} area boundaries into admin_areas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
