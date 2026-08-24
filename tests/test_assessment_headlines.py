"""The verdict line is the first thing read, and often the only thing quoted.

It may end up in front of a notary, a lender or a family, so it states the
finding and the next step and nothing else. It carried "green light", "clean
bill of health", "deal-breakers" and "get someone on the ground" — idiom stacked
on idiom, which also travels badly: a reader working in English as a second
language decodes the figure of speech before reaching the point.
"""

from __future__ import annotations

import pytest

from api.schemas.common import AssessmentLevel
from api.services.assessment import HEADLINES

LEVELS: list[AssessmentLevel] = ["low", "moderate", "higher", "unknown"]

#: Figures of speech that were in these lines, and near neighbours of them.
IDIOM = (
    "green light",
    "clean bill of health",
    "deal-breaker",
    "on the ground",
    "red flag",
    "go further",
    "stands out",
    "a couple of things",
)


class TestRegister:
    @pytest.mark.parametrize("level", LEVELS)
    def test_no_idiom(self, level: AssessmentLevel) -> None:
        lowered = HEADLINES[level].lower()

        for phrase in IDIOM:
            assert phrase not in lowered, f"{level}: {phrase}"

    @pytest.mark.parametrize("level", LEVELS)
    def test_no_contractions(self, level: AssessmentLevel) -> None:
        """"That's a green light" set the tone; the full form sets a different one."""
        for contraction in ("couldn't", "that's", "don't", "won't", "isn't"):
            assert contraction not in HEADLINES[level].lower()

    @pytest.mark.parametrize("level", LEVELS)
    def test_it_is_two_sentences(self, level: AssessmentLevel) -> None:
        """The finding, then what to do about it. Neither alone is enough."""
        sentences = [part for part in HEADLINES[level].split(". ") if part.strip()]

        assert len(sentences) == 2, HEADLINES[level]

    @pytest.mark.parametrize("level", LEVELS)
    def test_no_dashes_for_punctuation(self, level: AssessmentLevel) -> None:
        assert "—" not in HEADLINES[level]
        assert "–" not in HEADLINES[level]


class TestSubstance:
    def test_a_clear_reading_is_not_sold_as_a_guarantee(self) -> None:
        """The most dangerous line to get wrong: it is read as permission."""
        low = HEADLINES["low"].lower()

        assert "not confirmation" in low

    def test_the_worst_reading_names_a_concrete_next_step(self) -> None:
        """"Look into it" is not an action. A site visit is."""
        higher = HEADLINES["higher"].lower()

        assert "site visit" in higher
        assert "survey" in higher

    def test_a_middling_reading_does_not_read_as_a_verdict(self) -> None:
        moderate = HEADLINES["moderate"].lower()

        assert "disqualifying" in moderate

    def test_missing_data_is_not_reported_as_a_finding(self) -> None:
        """No data and no hazard are different answers."""
        unknown = HEADLINES["unknown"].lower()

        assert "not enough data" in unknown
        assert "hazard" not in unknown

    @pytest.mark.parametrize("level", LEVELS)
    def test_none_of_them_promises_safety(self, level: AssessmentLevel) -> None:
        lowered = HEADLINES[level].lower()

        for word in ("safe", "guarantee", "certified", "verified"):
            assert word not in lowered, f"{level}: {word}"
