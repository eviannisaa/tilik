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
        ],
    )
    def test_it_names_the_sources_it_actually_used(self, source: str) -> None:
        """Named, not hand-waved: they are checkable, and a reader can go read them."""
        assert source in DISCLAIMER

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
