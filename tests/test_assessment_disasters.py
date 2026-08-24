"""The verdict's disaster factors have to say what the data now holds.

Three things changed underneath them and the factors did not follow. The 150 km
GDACS feed was removed, so there is no "wider area" any more — every source
honours one radius from the checked coordinate. The archive became the only
source of casualty figures, which are the whole point of the section. And
tsunamis came from NOAA/NCEI with a measured height per observation.

Meanwhile the factor read: "12 recorded coastal erosion, drought, earthquake,
extreme weather, fire, flood, landslide, tsunami events within 25 km" — a tag
dump that never mentioned that a hundred people died.
"""

from __future__ import annotations

from api.schemas.location import (
    DisasterEvent,
    DisasterHistory,
    DisasterImpact,
)
from api.services.assessment import _disaster_factor, _tsunami_factor


def history(*events: DisasterEvent, **overrides) -> DisasterHistory:
    payload = {
        "radius_meters": 25_000,
        "searched_years": 25,
        "confidence": "high",
        "events": list(events),
        "covered_types": ["earthquake", "flood", "tsunami"],
    }
    payload.update(overrides)
    return DisasterHistory(**payload)


def archived(**overrides) -> DisasterEvent:
    row = {
        "id": "desinventar-1",
        "type": "flood",
        "hazard_types": ["flood"],
        "title": "Tangerang",
        "source": "BNPB DIBI (DesInventar)",
        "occurred_at": "2009-03-27T00:00:00+00:00",
        "scope": "regional",
        "distance_meters": 0.0,
        "distance_basis": "area_edge",
    }
    row.update(overrides)
    return DisasterEvent(**row)


def runup(**overrides) -> DisasterEvent:
    row = {
        "id": "ncei-1",
        "type": "tsunami",
        "hazard_types": ["tsunami"],
        "title": "Aceh, Sumatra",
        "source": "NOAA NCEI (tsunami runups)",
        "occurred_at": "2004-12-26T00:58:53+00:00",
        "scope": "point",
        "distance_meters": 700.0,
        "distance_basis": "measured",
        "water_height_m": 50.9,
    }
    row.update(overrides)
    return DisasterEvent(**row)


class TestHumanCost:
    def test_the_death_toll_leads(self) -> None:
        """It is the strongest thing the archive can say, and it was unsaid."""
        score, factor = _disaster_factor(
            history(archived(impact=DisasterImpact(deaths=100, missing=93, displaced=902)))
        )

        assert score == 3
        assert factor.label == "Recorded loss of life"
        assert "100 killed" in factor.detail
        assert factor.impact == "negative"

    def test_displacement_is_not_called_loss_of_life(self) -> None:
        """13,280 displaced and nobody killed is not a death toll."""
        _, factor = _disaster_factor(
            history(archived(impact=DisasterImpact(displaced=13_280)))
        )

        assert factor.label == "People displaced here"
        assert "13,280 displaced" in factor.detail

    def test_a_death_takes_the_label_even_when_displacement_is_larger(self) -> None:
        _, factor = _disaster_factor(
            history(archived(impact=DisasterImpact(deaths=1, displaced=600)))
        )

        assert factor.label == "Recorded loss of life"

    def test_the_worst_record_is_the_one_reported(self) -> None:
        score, factor = _disaster_factor(
            history(
                archived(id="a", impact=DisasterImpact(deaths=2)),
                archived(id="b", title="Bogor", impact=DisasterImpact(deaths=41)),
            )
        )

        assert "41 killed" in factor.detail
        assert "Bogor" in factor.detail


class TestTsunami:
    def test_the_height_is_reported_where_it_was_measured(self) -> None:
        score, factor = _tsunami_factor(history(runup()))

        assert score == 2
        assert "50.9 m" in factor.detail
        assert "from your coordinate" in factor.detail

    def test_it_does_not_compete_with_a_casualty_record(self) -> None:
        """Both are facts about the plot, so both are listed.

        Ordered into one slot, whichever came first won — and both orders were
        wrong: a 2013 flood with one death outranked the 50.9 m wave that reached
        Banda Aceh, and the reverse would bury a hundred deaths behind a
        half-metre swell.
        """
        events = history(
            archived(impact=DisasterImpact(deaths=1, displaced=600)), runup()
        )

        _, loss = _disaster_factor(events)
        _, wave = _tsunami_factor(events)

        assert loss.label == "Recorded loss of life"
        assert wave.label == "Tsunami reached here"

    def test_a_slight_swell_scores_lower_than_a_wall_of_water(self) -> None:
        small, _ = _tsunami_factor(history(runup(water_height_m=0.5)))
        large, _ = _tsunami_factor(history(runup(water_height_m=50.9)))

        assert small < large

    def test_no_tsunami_no_factor(self) -> None:
        assert _tsunami_factor(history(archived())) == (0, None)


class TestWording:
    def test_no_wider_area_claim_survives(self) -> None:
        """GDACS reached 150 km and was removed; one radius covers everything."""
        _, factor = _disaster_factor(history(archived()))

        assert "wider area" not in factor.label.lower()
        assert "wider area" not in factor.detail.lower()
        assert "25 km" in factor.detail

    def test_only_the_recurring_hazards_are_named(self) -> None:
        """Eight hazards listed alphabetically buried whichever one happens here."""
        _, factor = _disaster_factor(
            history(
                *[archived(id=f"f{n}", type="flood", hazard_types=["flood"]) for n in range(5)],
                archived(id="d", type="drought", hazard_types=["drought"]),
                archived(id="w", type="wildfire", hazard_types=["wildfire"]),
                archived(id="c", type="coastal erosion", hazard_types=["coastal erosion"]),
                archived(id="e", type="fire", hazard_types=["fire"]),
            )
        )

        # Ranked by how often each occurs, capped at three.
        assert factor.detail.count(",") <= 3
        assert "flood" in factor.detail

    def test_a_quiet_record_says_so_rather_than_implying_severity(self) -> None:
        _, factor = _disaster_factor(history(archived()))

        assert factor.impact == "neutral"
        assert "None with recorded casualties" in factor.detail


class TestMeasuredOnlyClaims:
    def test_an_archive_row_cannot_make_a_nearby_quake_claim(self) -> None:
        """It carries no position inside its district, so it has no distance.

        The old test for this used `event.scope == "point"`, but the guard it
        relied on read `event.distance_meters or float("inf")` — which maps 0.0
        to infinity, and 0.0 is exactly what an archive row carries when the
        coordinate falls inside its district.
        """
        _, factor = _disaster_factor(
            history(
                archived(
                    type="earthquake",
                    hazard_types=["earthquake"],
                    magnitude=7.5,
                    distance_meters=0.0,
                )
            )
        )

        assert factor.label == "Events on record nearby"

    def test_a_measured_epicentre_can(self) -> None:
        _, factor = _disaster_factor(
            history(
                DisasterEvent(
                    id="usgs-1",
                    type="earthquake",
                    hazard_types=["earthquake"],
                    title="16 km SSE of Palu, Indonesia",
                    source="USGS",
                    occurred_at="2018-09-28T10:25:04+00:00",
                    scope="point",
                    distance_meters=14_000.0,
                    distance_basis="measured",
                    magnitude=7.5,
                )
            )
        )

        assert factor.label == "Strong earthquake nearby"
        assert "Magnitude 7.5" in factor.detail
        assert "14 km from your coordinate" in factor.detail
