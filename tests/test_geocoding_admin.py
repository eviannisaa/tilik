"""Administrative hierarchy from Nominatim addresses.

Which key holds which Indonesian level is genuinely inconsistent, so these are
real payloads captured from the live service rather than invented ones. Reading
`county` as the kecamatan and `municipality` as the kabupaten produced
"Kabupaten Tangerang, Pagedangan, Banten" — the levels inverted.
"""

from __future__ import annotations

import pytest

from api.schemas.location import LocationInfo
from api.services.geocoding import admin_levels
from api.services.report import _build_area

# Captured from nominatim.openstreetmap.org/reverse, key order preserved: the
# service lists the most specific component first, which is what the code relies
# on rather than the key names.
ADDRESSES = {
    "bsd": {
        "suburb": "BSD City",
        "village": "Pagedangan",
        "municipality": "Pagedangan",
        "county": "Kabupaten Tangerang",
        "state": "Banten",
        "country": "Indonesia",
    },
    "bandung": {
        "suburb": "Kebon Pisang",
        "district": "Sumur Bandung",
        "city": "Kota Bandung",
        "state": "Jawa Barat",
        "postcode": "40112",
        "country": "Indonesia",
    },
    "blangpidie": {
        "hamlet": "DUSUN III",
        "town": "Blang Pidie",
        "municipality": "Blangpidie",
        "county": "Aceh Barat Daya",
        "state": "Aceh",
        "country": "Indonesia",
    },
    # Jakarta has no `state`: the province arrives as `city`.
    "pluit": {
        "city_block": "RW 05",
        "village": "Pluit",
        "suburb": "Penjaringan",
        "city_district": "Jakarta Utara",
        "city": "Daerah Khusus Ibukota Jakarta",
        "country": "Indonesia",
    },
}


def build(address: dict) -> LocationInfo:
    """Mirror what `geocoding.reverse` derives from an address."""
    levels = admin_levels(address)

    def at(from_end: int) -> str | None:
        return levels[-from_end] if len(levels) >= from_end else None

    return LocationInfo(
        latitude=0.0,
        longitude=0.0,
        locality=at(4) or (levels[0] if levels else None),
        district=at(3),
        city=at(2),
        province=address.get("state") or address.get("region") or at(1),
        country=address.get("country"),
    )


def test_levels_run_smallest_to_largest() -> None:
    assert admin_levels(ADDRESSES["bsd"]) == [
        "BSD City",
        "Pagedangan",
        "Kabupaten Tangerang",
        "Banten",
    ]


def test_a_level_repeated_under_two_keys_appears_once() -> None:
    # Pagedangan arrives as both `village` and `municipality`.
    assert admin_levels(ADDRESSES["bsd"]).count("Pagedangan") == 1


def test_non_administrative_keys_are_ignored() -> None:
    levels = admin_levels(ADDRESSES["pluit"])
    assert "RW 05" not in levels  # city_block
    assert "Indonesia" not in levels  # country


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("bsd", "Pagedangan, Kabupaten Tangerang, Banten"),
        ("bandung", "Sumur Bandung, Kota Bandung, Jawa Barat"),
        ("blangpidie", "Blangpidie, Aceh Barat Daya, Aceh"),
        ("pluit", "Penjaringan, Jakarta Utara, Daerah Khusus Ibukota Jakarta"),
    ],
)
def test_administrative_area_reads_kecamatan_kabupaten_province(key: str, expected: str) -> None:
    location = build(ADDRESSES[key])
    area = _build_area(0.0, 0.0, location, [])

    assert area.administrative_area == expected


def test_jakarta_province_is_recovered_without_a_state_key() -> None:
    location = build(ADDRESSES["pluit"])

    # `state` is absent for DKI Jakarta, so it has to come from the last level.
    assert "state" not in ADDRESSES["pluit"]
    assert location.province == "Daerah Khusus Ibukota Jakarta"
    assert location.city == "Jakarta Utara"


def test_each_level_lands_in_its_own_field() -> None:
    location = build(ADDRESSES["bsd"])

    assert location.locality == "BSD City"
    assert location.district == "Pagedangan"          # kecamatan
    assert location.city == "Kabupaten Tangerang"      # kabupaten
    assert location.province == "Banten"


def test_a_sparse_address_does_not_shift_levels_upward() -> None:
    # Only two levels available: they must fill the largest slots, not the smallest.
    location = build({"county": "Kabupaten Bogor", "state": "Jawa Barat"})

    assert location.city == "Kabupaten Bogor"
    assert location.province == "Jawa Barat"
    assert location.district is None
