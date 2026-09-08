"""What the report is, and what it is not.

Every figure in a report comes from a national model or a national archive:
InaRISK models a grid, DIBI records per district, USGS locates epicentres, NCEI
records where a wave was observed. None of them surveyed the plot being checked.
The gap between "the model says moderate here" and "this street floods every
February" is one only a person standing there can close, and the report has to
say so.

The text existed in the schema and in the frontend types, and was rendered
nowhere — it appeared only in test fixtures.
"""

from __future__ import annotations

import pytest

from api.schemas.report import DISCLAIMER, Assessment


class TestText:
    def test_it_says_the_report_is_for_reference(self) -> None:
        assert "reference only" in DISCLAIMER.lower()

    @pytest.mark.parametrize(
        "source",
        [
            pytest.param("InaRISK", id="inarisk"),
            pytest.param("DIBI", id="dibi"),
            pytest.param("USGS", id="usgs"),
            pytest.param("NOAA", id="noaa"),
            pytest.param("OpenTopography", id="opentopography"),
            pytest.param("OpenStreetMap", id="openstreetmap"),
            pytest.param("Nominatim", id="nominatim"),
            pytest.param("Google News", id="google-news"),
            pytest.param("World Air Quality Index", id="waqi"),
        ],
    )
    def test_it_names_the_sources_it_actually_used(self, source: str) -> None:
        """Named, not hand-waved: they are checkable, and a reader can go read them.

        Every provider `build_report` can put in `meta.sources` belongs here.
        The list once held the four hazard sources alone while the report was
        also reading elevation, place names, mapped water and places, local news
        and air quality, so a footer claiming to say where the readings came
        from named fewer than half of them.
        """
        assert source in DISCLAIMER

    def test_it_names_every_provider_the_report_can_report(self) -> None:
        """The guard on the guard: a new provider must not slip past the list.

        Read from the services rather than from one dictionary. Keying this on
        `FRIENDLY_PROVIDER_NAMES` alone left a hole big enough to matter:
        `NOAA NCEI` is a provider `meta.sources` really carries and is not in
        that dictionary, so a source added the same way would have passed.
        """
        from api.core.config import Settings
        from api.services import (
            air_quality,
            elevation,
            geocoding,
            inarisk,
            ncei_tsunami,
            news,
            opentopography,
            places,
            waterways,
        )
        from api.services.disasters import USGS_PROVIDER
        from api.services.report import FRIENDLY_PROVIDER_NAMES

        # Every provider slug a section can put in `meta.sources`, taken from
        # the modules that emit them.
        emitted = {
            air_quality.PROVIDER,
            elevation.PROVIDER,
            geocoding.PROVIDER,
            inarisk.PROVIDER,
            ncei_tsunami.NCEI_PROVIDER,
            news.PROVIDER,
            opentopography.PROVIDER,
            places.PROVIDER,
            waterways.PROVIDER,
            USGS_PROVIDER,
            *FRIENDLY_PROVIDER_NAMES,
        }

        # What each one is called in the disclaimer's own words.
        NAMED_AS = {
            "inarisk": "InaRISK",
            "opentopodata": "OpenTopography",
            "opentopography": "OpenTopography",
            "overpass": "OpenStreetMap",
            "nominatim": "Nominatim",
            "usgs": "USGS",
            "USGS": "USGS",
            "NOAA NCEI": "NOAA",
            "google-news": "Google News",
            "waqi": "World Air Quality Index",
        }

        # Neither of these is a source. One is Tilik's own estimate, reported
        # per check by `FloodInfo.basis`; the other is where an already named
        # source was stored.
        NOT_SOURCES = {"heuristic", "postgis"}

        unmapped = emitted - set(NAMED_AS) - NOT_SOURCES
        assert not unmapped, (
            "these providers can appear in a report and are not accounted for "
            f"in the disclaimer: {sorted(unmapped)}"
        )

        missing = sorted(
            {name for slug, name in NAMED_AS.items() if slug in emitted and name not in DISCLAIMER}
        )
        assert not missing, f"named in the report but not in the disclaimer: {missing}"

        # And the section is only in the report while it is switched on, so the
        # air-quality entry above is not conditional on a token being set.
        assert Settings().enable_air_quality is True

    def test_it_says_none_of_them_surveyed_this_plot(self) -> None:
        """The specific limit, rather than a general "may be inaccurate"."""
        assert "surveyed this plot" in DISCLAIMER

    def test_it_asks_for_a_visit_and_the_neighbours(self) -> None:
        """The two things that beat every model here, and cost nothing."""
        assert "walk the land" in DISCLAIMER
        assert "neighbours" in DISCLAIMER
        assert "rainy season" in DISCLAIMER

    def test_it_does_not_overclaim_certainty_anywhere(self) -> None:
        for phrase in ("guarantee", "accurate", "verified", "certified"):
            assert phrase not in DISCLAIMER.lower()

    @pytest.mark.parametrize(
        ("character", "name"),
        [
            pytest.param("\u2014", "em dash", id="em-dash"),
            pytest.param("\u2013", "en dash", id="en-dash"),
        ],
    )
    def test_it_uses_no_dashes_for_punctuation(
        self, character: str, name: str
    ) -> None:
        """Sentences instead. Each clause a dash carried stands on its own."""
        assert character not in DISCLAIMER, f"contains an {name}"


class TestDefault:
    def test_every_assessment_carries_it(self) -> None:
        """Nothing has to remember to attach it."""
        assessment = Assessment(level="low", headline="Nothing stands out.")

        assert assessment.disclaimer == DISCLAIMER
