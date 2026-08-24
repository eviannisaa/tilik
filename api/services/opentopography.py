"""Elevation from OpenTopography's Global DEM API.

OpenTopography serves DEM *rasters*, not point values, so a point query asks for
the smallest possible bounding box around the coordinate in ESRI ASCII Grid
format and reads the cell covering it. That keeps the payload to a few hundred
bytes.

A free API key is required (portal.opentopography.org → "Request an API key").
Without `OPENTOPOGRAPHY_API_KEY` set, this module reports itself unavailable and
the elevation service falls through to its key-less provider.
"""

from __future__ import annotations

import logging

from api.core.config import get_settings
from api.core.errors import TilikError, UpstreamUnavailableError
from api.core.http import fetch_text

logger = logging.getLogger("tilik.services.opentopography")

PROVIDER = "opentopography"

#: Half-width of the requested box in degrees (~110 m at the equator). Big
#: enough that SRTM's ~30 m grid always returns at least one cell.
_BOX_HALF_DEGREES = 0.0009


class AsciiGrid:
    """The subset of ESRI ASCII Grid we need: header plus a value lookup."""

    def __init__(
        self,
        *,
        ncols: int,
        nrows: int,
        xllcorner: float,
        yllcorner: float,
        cellsize: float,
        nodata: float,
        rows: list[list[float]],
    ) -> None:
        self.ncols = ncols
        self.nrows = nrows
        self.xllcorner = xllcorner
        self.yllcorner = yllcorner
        self.cellsize = cellsize
        self.nodata = nodata
        self.rows = rows

    def value_at(self, latitude: float, longitude: float) -> float | None:
        """Sample the cell containing a coordinate, or ``None`` for NODATA."""
        col = int((longitude - self.xllcorner) / self.cellsize)
        # ASCII grids are written top row first, so invert the row index.
        row_from_bottom = int((latitude - self.yllcorner) / self.cellsize)
        row = self.nrows - 1 - row_from_bottom

        # Clamp instead of failing: the requested point sits inside the box we
        # asked for, and rounding at the edge shouldn't lose the reading.
        col = min(max(col, 0), self.ncols - 1)
        row = min(max(row, 0), self.nrows - 1)

        try:
            value = self.rows[row][col]
        except IndexError:
            return None

        return None if value == self.nodata else value


def parse_ascii_grid(text: str) -> AsciiGrid:
    """Parse an ESRI ASCII Grid (`AAIGrid`) payload."""
    header: dict[str, float] = {}
    rows: list[list[float]] = []
    expected = {"ncols", "nrows", "xllcorner", "yllcorner", "cellsize"}

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        first = line.split(None, 1)[0].lower()
        if first in expected or first == "nodata_value":
            key, raw = line.split(None, 1)
            header[key.lower()] = float(raw.strip())
            continue

        rows.append([float(part) for part in line.split()])

    missing = expected - header.keys()
    if missing:
        raise UpstreamUnavailableError(
            detail=f"OpenTopography grid is missing header fields: {sorted(missing)}"
        )
    if not rows:
        raise UpstreamUnavailableError(detail="OpenTopography returned a grid with no data rows")

    return AsciiGrid(
        ncols=int(header["ncols"]),
        nrows=int(header["nrows"]),
        xllcorner=header["xllcorner"],
        yllcorner=header["yllcorner"],
        cellsize=header["cellsize"],
        nodata=header.get("nodata_value", -9999.0),
        rows=rows,
    )


def is_configured() -> bool:
    return bool(get_settings().opentopography_api_key)


async def get_elevation(latitude: float, longitude: float) -> float | None:
    """Elevation in metres, or ``None`` if the DEM has no data for the point."""
    settings = get_settings()
    if not settings.opentopography_api_key:
        raise UpstreamUnavailableError(detail="OPENTOPOGRAPHY_API_KEY is not set")

    half = _BOX_HALF_DEGREES
    text = await fetch_text(
        settings.opentopography_api_url,
        provider=PROVIDER,
        params={
            "demtype": settings.opentopography_dem_type,
            "south": latitude - half,
            "north": latitude + half,
            "west": longitude - half,
            "east": longitude + half,
            "outputFormat": "AAIGrid",
            "API_Key": settings.opentopography_api_key,
        },
    )

    # Errors come back as a small XML document rather than a grid.
    if text.lstrip().startswith("<"):
        snippet = text.strip()[:160]
        logger.warning("OpenTopography rejected the request: %s", snippet)
        raise UpstreamUnavailableError(detail=f"OpenTopography error: {snippet}")

    try:
        grid = parse_ascii_grid(text)
    except TilikError:
        raise
    except ValueError as exc:
        raise UpstreamUnavailableError(detail="OpenTopography grid was unparseable") from exc

    return grid.value_at(latitude, longitude)
