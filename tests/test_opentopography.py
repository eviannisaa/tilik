"""Parser tests for the OpenTopography ASCII-grid response.

These matter because the live endpoint needs an API key, so the parse path would
otherwise stay untested until someone deploys with one.
"""

from __future__ import annotations

import pytest

from api.core.errors import UpstreamUnavailableError
from api.services.opentopography import AsciiGrid, parse_ascii_grid

CELL = 0.000277777777778  # SRTM's 1-arcsecond spacing

# A real-shaped AAIGrid response: a 3x3 box centred on Bandung
# (-6.9175, 107.6191), so the lower-left corner sits 1.5 cells away.
SAMPLE = f"""ncols        3
nrows        3
xllcorner    {107.6191 - 1.5 * CELL:.12f}
yllcorner    {-6.9175 - 1.5 * CELL:.12f}
cellsize     {CELL:.15f}
NODATA_value -32768
 701 700 698
 699 698 697
 697 696 694
"""


def cell_centre(grid: AsciiGrid, row: int, col: int) -> tuple[float, float]:
    """Latitude/longitude at the centre of one cell, top row first."""
    longitude = grid.xllcorner + (col + 0.5) * grid.cellsize
    row_from_bottom = grid.nrows - 1 - row
    latitude = grid.yllcorner + (row_from_bottom + 0.5) * grid.cellsize
    return latitude, longitude


def test_parses_header_and_rows() -> None:
    grid = parse_ascii_grid(SAMPLE)

    assert (grid.ncols, grid.nrows) == (3, 3)
    assert grid.cellsize == pytest.approx(CELL)
    assert grid.nodata == -32768
    assert grid.rows == [[701, 700, 698], [699, 698, 697], [697, 696, 694]]


def test_requested_point_lands_in_the_middle_cell() -> None:
    grid = parse_ascii_grid(SAMPLE)

    # The box is built around this coordinate, so it must resolve to rows[1][1].
    assert grid.value_at(-6.9175, 107.6191) == 698


@pytest.mark.parametrize(
    ("row", "col", "expected"),
    [(0, 0, 701), (0, 2, 698), (1, 1, 698), (2, 0, 697), (2, 2, 694)],
)
def test_every_cell_is_addressable(row: int, col: int, expected: float) -> None:
    grid = parse_ascii_grid(SAMPLE)
    latitude, longitude = cell_centre(grid, row, col)

    assert grid.value_at(latitude, longitude) == expected


def test_nodata_becomes_none() -> None:
    grid = parse_ascii_grid(SAMPLE.replace(" 699 698 697", " 699 -32768 697"))

    assert grid.value_at(-6.9175, 107.6191) is None


def test_points_outside_the_box_clamp_to_the_nearest_cell() -> None:
    grid = parse_ascii_grid(SAMPLE)

    # Rounding at the edge of the requested box must not lose the reading.
    assert grid.value_at(-6.9200, 107.6100) == 697
    assert grid.value_at(-6.9100, 107.6300) == 698


def test_missing_header_is_rejected() -> None:
    with pytest.raises(UpstreamUnavailableError):
        parse_ascii_grid("ncols 3\nnrows 3\n 1 2 3\n")


def test_grid_with_no_rows_is_rejected() -> None:
    header = "\n".join(SAMPLE.splitlines()[:6])

    with pytest.raises(UpstreamUnavailableError):
        parse_ascii_grid(header)
