"""Reading BNPB's loss archive without quietly losing the worst of it.

Two mistakes this pins, both found by spot-checking Palu against the import.

The first was a category decision that looked safe. `GEMPA BUMI DAN TSUNAMI` is
27 records against 649 pure earthquakes, so folding it into `tsunami` seemed
like rounding — until those 27 turned out to be Aceh 2004 and Palu 2018, holding
170,791 of the archive's 188,621 combined earthquake deaths. It would have moved
91% of them out of `earthquake`, and it misdescribes Palu, where the shaking and
the liquefaction at Petobo, Balaroa and Jono Oge killed far more people than the
wave. Small record counts are not small events.

The second is that a reported zero and an unrecorded zero look identical in the
data and mean opposite things. DesInventar distinguishes them with a companion
flag, and `damnificados` never once uses the "reported zero" value — so 29,208
of 33,010 events carry a displacement count of 0 that means "nobody wrote it
down". Reading those as zero would print an all-clear the archive never gave.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "import_desinventar",
    Path(__file__).resolve().parent.parent / "scripts" / "import_desinventar.py",
)
assert _SPEC and _SPEC.loader
importer = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(importer)


def record(**overrides: str) -> dict[str, str]:
    """A DesInventar event row, defaulting to "nothing was recorded"."""
    base = {
        "evento": "BANJIR",
        "fechano": "2018",
        "fechames": "9",
        "fechadia": "28",
        "name0": "SULAWESI TENGAH",
        "name1": "KOTA PALU",
        "magnitud2": "",
        "muertos": "0",
        "hay_muertos": "0",
        "desaparece": "0",
        "hay_deasparece": "0",
        "heridos": "0",
        "hay_heridos": "0",
        "evacuados": "0",
        "hay_evacuados": "0",
        "vivdest": "0",
        "hay_vivdest": "0",
        "vivafec": "0",
        "hay_vivafec": "0",
    }
    return {**base, **overrides}


class TestEventTypes:
    def test_combined_quake_and_tsunami_keeps_both_hazards(self) -> None:
        """Palu and Aceh must not be filed away as "tsunami"."""
        assert importer.EVENT_TYPES["GEMPA BUMI DAN TSUNAMI"] == "earthquake and tsunami"

    def test_it_is_distinct_from_either_half(self) -> None:
        combined = importer.EVENT_TYPES["GEMPA BUMI DAN TSUNAMI"]
        assert combined != importer.EVENT_TYPES["TSUNAMI"]
        assert combined != importer.EVENT_TYPES["GEMPA BUMI"]

    def test_non_ground_categories_are_skipped_not_mapped(self) -> None:
        """Transport crashes and riots say nothing about a plot of land."""
        for category in ("KECELAKAAN TRANSPORTASI", "KONFLIK / KERUSUHAN SOSIAL"):
            assert category in importer.SKIPPED_TYPES
            assert category not in importer.EVENT_TYPES

    def test_every_skipped_category_is_deliberate(self) -> None:
        """A category cannot be both mapped and skipped."""
        assert not (importer.SKIPPED_TYPES & importer.EVENT_TYPES.keys())


class TestImpactFlags:
    def test_a_real_figure_is_kept(self) -> None:
        """Kota Palu, as the archive records it."""
        impact = importer._impact(
            record(
                muertos="3624",
                hay_muertos="-1",
                desaparece="570",
                hay_deasparece="-1",
                evacuados="52415",
                hay_evacuados="-1",
                vivdest="18107",
                hay_vivdest="-1",
            )
        )
        assert impact["deaths"] == 3624
        assert impact["missing"] == 570
        assert impact["displaced"] == 52_415
        assert impact["houses_destroyed"] == 18_107

    def test_a_reported_zero_stays_zero(self) -> None:
        impact = importer._impact(record(muertos="0", hay_muertos="1"))
        assert impact["deaths"] == 0

    def test_an_unrecorded_count_becomes_null(self) -> None:
        """The distinction the whole mapping exists for.

        Same stored value, opposite meaning: flag 1 is the archive saying "none",
        flag 0 is the archive saying nothing.
        """
        impact = importer._impact(record(evacuados="0", hay_evacuados="0"))
        assert impact["displaced"] is None

    def test_an_unexpected_flag_is_treated_as_unknown(self) -> None:
        """Guessing is worse than admitting the value is not understood."""
        assert importer._impact(record(muertos="9", hay_muertos=""))["deaths"] is None

    def test_missing_uses_the_exports_misspelt_field(self) -> None:
        """`hay_deasparece` is misspelt at source; reading `hay_desaparece`
        silently returned None for every event in the archive."""
        assert importer.IMPACT_FIELDS["missing"] == ("desaparece", "hay_deasparece")


class TestHazardMembership:
    """A compound event must belong to both of its hazards.

    This is the same bug twice. Filing Palu under `tsunami` hid it from
    earthquakes; giving it the compound label `earthquake and tsunami` and
    nothing else hid it from *both*, because `covered_types` is built from what
    events claim to be — and an absence there means "never searched". A
    128,728-death tsunami would have rendered as "no tsunami data for this
    area". Splitting the row in two would double-count every death instead, so
    the row stays whole and lists its hazards.
    """

    def test_the_compound_event_claims_both_hazards(self) -> None:
        assert importer.HAZARD_TYPES["earthquake and tsunami"] == ["earthquake", "tsunami"]

    def test_a_single_hazard_event_needs_no_entry(self) -> None:
        """The fallback keeps the mapping to genuine exceptions only."""
        assert "flood" not in importer.HAZARD_TYPES
        assert importer.HAZARD_TYPES.get("flood", ["flood"]) == ["flood"]

    def test_every_hazard_named_is_a_real_atomic_type(self) -> None:
        """A compound must decompose into types other sources also emit,
        otherwise the hazard vocabulary silently forks."""
        atomic = set(importer.EVENT_TYPES.values()) - set(importer.HAZARD_TYPES)
        for hazards in importer.HAZARD_TYPES.values():
            for hazard in hazards:
                assert hazard in atomic, hazard

    def test_the_api_fills_hazard_types_from_type_by_default(self) -> None:
        from api.schemas.location import DisasterEvent

        event = DisasterEvent(id="x", type="flood", title="t", source="s")
        assert event.hazard_types == ["flood"]

    def test_the_api_preserves_an_explicit_hazard_list(self) -> None:
        from api.schemas.location import DisasterEvent

        event = DisasterEvent(
            id="x",
            type="earthquake and tsunami",
            hazard_types=["earthquake", "tsunami"],
            title="Palu",
            source="BNPB DIBI (DesInventar)",
        )
        assert event.hazard_types == ["earthquake", "tsunami"]


class TestScope:
    """Position precision has three tiers, and the coarsest is not a location.

    The bundled boundaries hold 428 regencies against today's ~514: Indonesia
    kept splitting them. Events in a regency created after the shapefile fall
    back to the province centroid, up to ~130 km off — Palu's 289 deaths in
    Sigi land in empty mountains 130 km east. That would surface them for a pin
    near an arbitrary point and hide them from Sigi itself, so those rows are
    marked instead of being passed off as merely approximate.
    """

    def test_a_regency_match_is_regional(self) -> None:
        assert importer.SCOPE_BY_LEVEL["id1"] == "regional"

    def test_a_province_fallback_is_marked_apart(self) -> None:
        assert importer.SCOPE_BY_LEVEL["id0"] == "provincial"

    def test_every_admin_level_has_a_scope(self) -> None:
        """A new level must not default silently to a precision it lacks."""
        for _, stem, _code, _record_name, _dbf_name in importer.ADMIN_LEVELS:
            assert stem in importer.SCOPE_BY_LEVEL

    def test_the_scopes_are_ones_the_api_accepts(self) -> None:
        from api.schemas.location import DisasterEvent

        allowed = DisasterEvent.model_fields["scope"].annotation.__args__
        for scope in importer.SCOPE_BY_LEVEL.values():
            assert scope in allowed


class TestDates:
    def test_a_full_date_is_read(self) -> None:
        occurred = importer._occurred_at(record())
        assert occurred is not None
        assert (occurred.year, occurred.month, occurred.day) == (2018, 9, 28)

    def test_a_missing_month_falls_back_to_january(self) -> None:
        """DIBI's older records often carry a year alone."""
        occurred = importer._occurred_at(record(fechano="1815", fechames="0", fechadia="0"))
        assert occurred is not None
        assert (occurred.year, occurred.month, occurred.day) == (1815, 1, 1)

    def test_an_impossible_day_keeps_the_month(self) -> None:
        occurred = importer._occurred_at(record(fechames="2", fechadia="31"))
        assert occurred is not None
        assert (occurred.year, occurred.month) == (2018, 2)

    def test_no_year_means_no_date(self) -> None:
        assert importer._occurred_at(record(fechano="")) is None


class TestMagnitude:
    def test_the_archive_never_supplies_one(self) -> None:
        """`magnitud2` is empty in all 33,010 records, Palu included."""
        assert importer._magnitude(record()) == (None, None, None)

    def test_a_future_export_would_be_read_as_unlabelled(self) -> None:
        value, scale, source = importer._magnitude(record(magnitud2="7,5"))
        assert value == 7.5
        # DIBI names no scale, so it must not be passed off as a USGS one.
        assert scale == "m"
        assert source is not None

    @pytest.mark.parametrize("raw", ["", "n/a", "0", "99"])
    def test_unusable_values_are_ignored(self, raw: str) -> None:
        assert importer._magnitude(record(magnitud2=raw)) == (None, None, None)


class TestPlaceNames:
    def test_the_most_specific_name_wins(self) -> None:
        assert importer._place(record(name2="PALU SELATAN")) == "Palu Selatan"

    def test_it_falls_back_up_the_hierarchy(self) -> None:
        assert importer._place(record(name1="", name2="")) == "Sulawesi Tengah"

    def test_short_words_stay_upper_case(self) -> None:
        """Indonesian place names are full of them — DKI, NTT, Kab."""
        assert importer._place(record(name1="DKI JAKARTA", name2="")) == "DKI Jakarta"


class TestParentRegency:
    """Rescuing areas the 2020-era boundaries never had.

    Indonesia kept subdividing its regencies, so 428 boundaries have to serve
    ~514 areas. Falling back to the province centroid put Serpong's own five
    recorded floods 63 km away — outside a 50 km search — while neighbouring
    Jakarta's floods showed up as if they were local. Indonesian naming makes
    the parent recoverable: a new area is its parent's name plus a qualifier.

    Two guards matter as much as the match itself. Exact names are tried first,
    or `KOTA BOGOR` would collapse onto the surrounding regency `BOGOR`. And the
    search is confined to one province, which is what caught the matches that
    were plainly wrong — `BATU BARA` in North Sumatra had resolved to Kota
    `BATU` in East Java, 1,500 km away.
    """

    #: A slice of the real boundary names, keyed "PROVINCE|NAME" as loaded.
    BOUNDARIES = {
        "BANTEN|TANGERANG": (-6.19, 106.56),
        "JAWA BARAT|BOGOR": (-6.55, 106.80),
        "JAWA BARAT|KOTA BOGOR": (-6.60, 106.80),
        "JAWA TIMUR|KOTA BATU": (-7.87, 112.52),
        "SUMATERA UTARA|ASAHAN": (2.79, 99.55),
        "NANGGROE ACEH DARUSSALAM|PIDIE": (5.10, 95.95),
        "JAWA TENGAH|PEMALANG": (-7.02, 109.40),
    }

    def test_it_finds_the_parent_of_a_split_off_city(self) -> None:
        assert (
            importer.resolve_parent("KOTA TANGERANG SELATAN", "BANTEN", self.BOUNDARIES)
            == "TANGERANG"
        )

    def test_it_does_not_cross_a_province(self) -> None:
        """`BATU BARA` is in North Sumatra; Kota `BATU` is in East Java."""
        assert (
            importer.resolve_parent("BATU BARA", "SUMATERA UTARA", self.BOUNDARIES) is None
        )

    def test_it_matches_whole_words_only(self) -> None:
        """`PEMALANG` must never be read as containing `MALANG`."""
        assert importer.resolve_parent("MALANG SELATAN", "JAWA TENGAH", self.BOUNDARIES) is None

    def test_a_single_word_name_has_no_recoverable_parent(self) -> None:
        """Sigi's parent is Donggala, which its name does not reveal."""
        assert importer.resolve_parent("SIGI", "SULAWESI TENGAH", self.BOUNDARIES) is None

    def test_province_renames_are_aliased(self) -> None:
        """The archive says ACEH; the boundaries still say the old long name."""
        assert importer._province_key("Aceh") == "NANGGROE ACEH DARUSSALAM"
        assert (
            importer.resolve_parent("PIDIE JAYA", "ACEH", self.BOUNDARIES) == "PIDIE"
        )

    def test_normalising_keeps_the_area_type(self) -> None:
        """Dropping KOTA would place a city's events in the enclosing regency."""
        assert importer._normalise_area("  kota   bogor ") == "KOTA BOGOR"
        assert importer._normalise_area("Kabupaten Malang") == "KAB. MALANG"

    def test_a_parent_match_is_still_a_regency(self) -> None:
        """It is a real regency boundary, so it must not be marked provincial."""
        assert importer.SCOPE_BY_LEVEL["id1-parent"] == "regional"
