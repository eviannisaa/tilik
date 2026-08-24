"""A failed Overpass query must not read as an empty neighbourhood.

Overpass reports some failures inside a successful response: a query that runs
out of time comes back as HTTP 200, an empty `elements` array, and a `remark`
naming the error. Trusted as data, that is indistinguishable from a healthy
answer for a place where nothing is mapped, so a failed lookup became the claim
that a plot has no clinic, no school and no shop within 1.5 km.

Observed from the live endpoint:

    {"elements": [], "remark": "runtime error: Query timed out in \\"query\\"
     at line 1 after 2 seconds."}
"""

from __future__ import annotations

import pytest

from api.core.errors import UpstreamUnavailableError
from api.services.overpass import elements_of


def test_an_error_remark_is_a_failure_not_an_empty_result() -> None:
    payload = {
        "elements": [],
        "remark": 'runtime error: Query timed out in "query" at line 1 after 2 seconds.',
    }

    with pytest.raises(UpstreamUnavailableError):
        elements_of(payload, provider="overpass")


def test_the_reason_travels_with_the_failure() -> None:
    """So the footer can say why, instead of only that something went wrong."""
    payload = {"elements": [], "remark": "runtime error: out of memory"}

    with pytest.raises(UpstreamUnavailableError) as raised:
        elements_of(payload, provider="overpass")

    assert "out of memory" in str(raised.value.detail)


def test_a_genuinely_empty_answer_stays_empty() -> None:
    """No remark means Overpass looked and found nothing, which is a finding."""
    assert elements_of({"elements": []}, provider="overpass") == []


def test_a_remark_with_data_keeps_the_data() -> None:
    """Overpass also uses `remark` for notices, and those still carry results.

    Discarding a partial answer would throw away everything it did find.
    """
    payload = {
        "elements": [{"id": 1, "tags": {"amenity": "hospital"}}],
        "remark": "runtime error: Query run out of memory in some places",
    }

    assert len(elements_of(payload, provider="overpass")) == 1


def test_non_dictionary_elements_are_dropped() -> None:
    payload = {"elements": [{"id": 1}, "not an element", None]}

    assert elements_of(payload, provider="overpass") == [{"id": 1}]


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(None, id="none"),
        pytest.param([], id="list"),
        pytest.param("text", id="string"),
    ],
)
def test_a_body_that_is_not_a_response_yields_nothing(payload) -> None:
    assert elements_of(payload, provider="overpass") == []


def test_a_blank_remark_is_not_an_error() -> None:
    assert elements_of({"elements": [], "remark": "   "}, provider="overpass") == []


class TestFallbackCoverage:
    """An empty answer from a mirror is not evidence that an area is empty.

    `overpass.osm.ch` proved it: 30 banks in Zurich, zero in Indonesia, because
    its database holds Switzerland only. It answers 200, so nothing marked the
    section unavailable, and a plot in Serpong with 120 mapped places was
    reported as having none. A mirror that lies quietly is worse than one that
    fails outright.
    """

    def test_an_empty_answer_from_a_fallback_is_a_failure(self) -> None:
        with pytest.raises(UpstreamUnavailableError):
            elements_of({"elements": []}, provider="overpass", trust_empty=False)

    def test_an_empty_answer_from_the_primary_is_a_finding(self) -> None:
        """There it means the catalogue looked and found nothing."""
        assert elements_of({"elements": []}, provider="overpass", trust_empty=True) == []

    def test_a_fallback_that_returns_data_is_trusted(self) -> None:
        """The guard is about emptiness, not about mirrors being second-class."""
        payload = {"elements": [{"id": 1, "tags": {"amenity": "school"}}]}

        assert len(elements_of(payload, provider="overpass", trust_empty=False)) == 1

    def test_the_primary_is_trusted_by_default(self) -> None:
        """So a caller that does not care cannot accidentally get the strict rule."""
        assert elements_of({"elements": []}, provider="overpass") == []
