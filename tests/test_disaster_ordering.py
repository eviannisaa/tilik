"""Ranking stored events by distance alone loses the worst of them.

Imported DIBI rows carry a regency centroid, not a site, so every event in one
regency ties *exactly* on distance: 176 rows sit 2,923 m from a pin on Banda
Aceh's beach. Under a plain `ORDER BY distance … LIMIT 12` the tie broke however
Postgres felt, and a 2009 house fire that displaced nobody pushed the 2004
tsunami — 128,728 dead, 37,063 missing — out of the list. The report then said
"Not searched here: tsunami" while the row sat in the database.

Two things were wrong and both are pinned here: the ordering had no tiebreak,
and the query fetched exactly as many rows as the section would show, leaving
`_select_events` no candidates to spread across hazard types.
"""

from __future__ import annotations

from api.db import repository
from api.models import DisasterEvent
from api.schemas.location import DisasterEvent as DisasterEventSchema
from api.services import disasters as disasters_service


class TestSeverityTiebreak:
    """One definition of the ordering, shared by both hand-written statements.

    `disasters_near` and `_ANALYSE_LOCATION` are both raw SQL now — the previous
    SQLAlchemy version could not express the query shape a spatial index can
    serve — so the drift these tests were written to catch is between two
    strings. `_severity_order_sql` is what removes it.
    """

    def test_it_ranks_by_who_was_harmed(self) -> None:
        """Deaths first, then the missing, the displaced, then homes lost."""
        # By position in the clause, not by splitting on commas: `COALESCE(x, 0)`
        # contains one.
        sql = repository._severity_order_sql()
        positions = [sql.index(column) for column in repository._SEVERITY_COLUMNS]

        assert positions == sorted(positions)
        assert repository._SEVERITY_COLUMNS == (
            "deaths",
            "missing",
            "displaced",
            "houses_destroyed",
        )

    def test_every_impact_term_sorts_worst_first(self) -> None:
        sql = repository._severity_order_sql()

        for column in repository._SEVERITY_COLUMNS:
            assert f"COALESCE({column}, 0) DESC" in sql

    def test_a_null_count_does_not_win(self) -> None:
        """NULL means "no figure published", and must sort below a real one.

        Postgres puts NULL first under DESC by default, so an unrecorded death
        toll would outrank a known one without the COALESCE.
        """
        sql = repository._severity_order_sql()

        for column in repository._SEVERITY_COLUMNS:
            assert f"COALESCE({column}" in sql

    def test_recency_settles_a_full_tie(self) -> None:
        sql = repository._severity_order_sql()
        last = sql[sql.index("occurred_at") :]

        assert "DESC" in last
        # Postgres puts NULL first under DESC, and an undated record must not
        # outrank a dated one.
        assert "NULLS LAST" in last

    def test_an_alias_qualifies_every_column(self) -> None:
        """Both statements use it inside a join, where a bare name is ambiguous."""
        sql = repository._severity_order_sql("d")

        for column in (*repository._SEVERITY_COLUMNS, "occurred_at"):
            assert f"d.{column}" in sql
            # And never the bare name, which would be ambiguous in the join.
            assert f"({column}" not in sql

    def test_both_statements_share_it(self) -> None:
        """The drift this class exists to catch."""
        combined = str(repository._ANALYSE_LOCATION)

        assert repository._severity_order_sql("e") in combined
        assert repository._severity_order_sql("d") in combined


class TestCandidatePool:
    def test_more_rows_are_read_than_shown(self) -> None:
        """Otherwise the type-diversity pass has nothing to choose between."""
        assert disasters_service.STORED_FETCH_LIMIT > disasters_service.MAX_EVENTS

    def test_the_pool_covers_a_busy_regency(self) -> None:
        """Banda Aceh alone qualifies 176 rows; a pool of 12 saw almost none."""
        assert disasters_service.STORED_FETCH_LIMIT >= 72


class TestAreaCap:
    """One district must not take the whole list.

    Imported records carry their district's centroid, so every row in a district
    ties on distance and the district whose centre happens to be nearest wins
    everything. Around Serpong that was Kota Jakarta Selatan: 105 rows at 16 km,
    against Kota Tangerang Selatan — the district the pin is actually inside —
    at 18 km. All 72 candidate rows came back Jakarta's, so the selection step
    never saw another district, and a land check in Serpong displayed Jakarta's
    disaster history while Serpong's own five floods and Tangerang's 100-death
    flood of 2009 were invisible. Two kilometres of centroid arithmetic.

    The cap therefore has to live in the query, not only in the selection: a
    client-side cap can shrink a monopolised list but cannot diversify it.
    """

    def test_a_cap_is_set(self) -> None:
        assert disasters_service.MAX_EVENTS_PER_AREA >= 1
        assert disasters_service.MAX_EVENTS_PER_AREA < disasters_service.MAX_EVENTS

    def test_the_cap_is_applied_in_the_query(self) -> None:
        """The candidate pool is where the monopoly happened."""
        sql = str(repository._ANALYSE_LOCATION)
        assert "rank_in_area" in sql
        assert "event_per_area" in sql
        assert "PARTITION BY" in sql

    def test_measured_rows_are_never_capped(self) -> None:
        """Each epicentre is its own location, so it cannot crowd a district out.

        They have no `area_name`, so the partition key falls back to their id —
        giving every measured row a partition of one.
        """
        sql = str(repository._ANALYSE_LOCATION)
        assert "COALESCE(e.area_name, 'measured-' || e.id)" in sql

    def test_the_cap_keeps_the_worst_of_each_area(self) -> None:
        """Ranking inside a partition is by harm, so a cap keeps what matters."""
        sql = str(repository._ANALYSE_LOCATION)
        window = sql[sql.index("PARTITION BY") : sql.index("AS rank_in_area")]
        for column in ("deaths", "missing", "displaced", "houses_destroyed"):
            assert column in window

    def test_selection_caps_areas_too(self) -> None:
        """A second net over the merged live-plus-stored list."""
        events = [
            DisasterEventSchema(
                id=f"a{index}",
                type="flood",
                area_name="Kota Jakarta Selatan",
                title="Flood",
                source="BNPB DIBI (DesInventar)",
                scope="regional",
                distance_meters=16_000.0,
            )
            for index in range(8)
        ] + [
            DisasterEventSchema(
                id="own",
                type="drought",
                area_name="Kota Tangerang Selatan",
                title="Drought",
                source="BNPB DIBI (DesInventar)",
                scope="regional",
                distance_meters=18_000.0,
            )
        ]

        selected = disasters_service._select_events(events, limit=12, per_type=3)
        areas = [event.area_name for event in selected]

        assert areas.count("Kota Jakarta Selatan") <= disasters_service.MAX_EVENTS_PER_AREA
        # The nearer district must not squeeze the pin's own district out.
        assert "Kota Tangerang Selatan" in areas


class TestZeroDistance:
    """An event at the pin must sort first, not last.

    `event.distance_meters or inf` was meant to push unknown distances to the
    end, but 0.0 is falsy, so it pushed *zero* there too. Harmless while every
    area-level row sat on a centroid — no row was ever exactly 0 m away. Area
    boundaries changed that: a pin inside a district is 0 m from it, so the one
    district the reader is actually standing in dropped to the bottom of their
    own report.
    """

    @staticmethod
    def _event(identifier: str, distance: float | None) -> DisasterEventSchema:
        return DisasterEventSchema(
            id=identifier,
            type="flood",
            area_name=identifier,
            title=identifier,
            source="BNPB DIBI (DesInventar)",
            scope="regional",
            distance_meters=distance,
        )

    def test_zero_sorts_first(self) -> None:
        events = [
            self._event("far", 20_000.0),
            self._event("here", 0.0),
            self._event("near", 5_000.0),
        ]
        order = [e.id for e in disasters_service._select_events(events, 12, 3)]
        assert order[0] == "here"

    def test_unknown_still_sorts_last(self) -> None:
        events = [self._event("unknown", None), self._event("here", 0.0)]
        order = [e.id for e in disasters_service._select_events(events, 12, 3)]
        assert order == ["here", "unknown"]

    def test_the_key_separates_zero_from_missing(self) -> None:
        assert disasters_service._by_distance(self._event("a", 0.0)) == 0.0
        assert disasters_service._by_distance(self._event("b", None)) == float("inf")


class TestSignificanceRanking:
    """A short list has to hold what matters, not what is marginally nearest.

    The NTT earthquake of 15 August 2026 is the case. Its M7.7 sat 4.9 km from a
    pin on the epicentre, while three M5.0 aftershocks sat 2.1, 2.2 and 4.3 km
    away — so ranking a hazard's rows by distance and keeping three showed the
    aftershocks and dropped the earthquake the reader had come to look up. A
    magnitude 7.7 five kilometres off dominates a magnitude 5 two kilometres off
    by any reading a person would recognise.

    Distance still decides the display order, and still breaks ties. It just no
    longer decides what survives.
    """

    @staticmethod
    def _quake(identifier: str, magnitude: float, mmi: float | None, km: float):
        return DisasterEventSchema(
            id=identifier,
            type="earthquake",
            title=identifier,
            magnitude=magnitude,
            intensity_mmi=mmi,
            source="USGS",
            scope="point",
            distance_meters=km * 1000,
        )

    def test_the_mainshock_survives_nearer_aftershocks(self) -> None:
        events = [
            self._quake("after-1", 5.0, None, 2.1),
            self._quake("after-2", 5.0, 2.2, 2.2),
            self._quake("after-3", 5.0, None, 4.3),
            self._quake("mainshock", 7.7, 7.9, 4.9),
        ]
        selected = disasters_service._select_events(events, limit=3, per_type=3)
        assert "mainshock" in [e.id for e in selected]

    def test_distance_still_breaks_a_tie(self) -> None:
        events = [
            self._quake("far", 6.0, 6.0, 20.0),
            self._quake("near", 6.0, 6.0, 2.0),
        ]
        ranked = sorted(events, key=disasters_service._significance, reverse=True)
        assert [e.id for e in ranked] == ["near", "far"]

    def test_the_mainshock_survives_even_though_it_reads_second(self) -> None:
        """Ranking is about membership; the list itself reads nearest-first.

        The distinction is the whole point of keeping `_significance`. A plain
        nearest-three cut *dropped* the M7.7 in favour of three closer M5.0
        aftershocks, which is a lost event. Listing it below a nearer aftershock
        is only a reading order, and the reader can see both.
        """
        events = [
            self._quake("mainshock", 7.7, 7.9, 4.9),
            self._quake("aftershock", 5.0, None, 2.1),
        ]
        selected = disasters_service._select_events(events, limit=12, per_type=3)

        assert {e.id for e in selected} == {"mainshock", "aftershock"}
        assert [e.id for e in selected] == ["aftershock", "mainshock"]

    def test_magnitude_outranks_a_borrowed_intensity(self) -> None:
        """USGS reports the event's highest intensity, not the intensity here.

        This asserted the opposite while every source stopped at 25 km, where an
        event's maximum shaking and the shaking at the pin were near enough the
        same thing. Over 200 km they are not: an M5.8 at 103 km carried MMI 8.9
        recorded near Poso, and ranking on it put that above the M7.5 at 72 km
        that levelled Palu. Magnitude describes the event itself and cannot
        silently belong to somewhere else.
        """
        distant = self._quake("distant", 5.5, 8.9, 103.0)
        bigger = self._quake("bigger", 7.5, 8.4, 71.6)
        ranked = sorted([distant, bigger], key=disasters_service._significance, reverse=True)
        assert ranked[0].id == "bigger"

    def test_intensity_still_ranks_a_record_with_no_magnitude(self) -> None:
        """It is the best a record can say when its magnitude is missing."""
        shaken = self._quake("shaken", None, 7.0, 10.0)
        quiet = self._quake("quiet", None, 3.0, 10.0)
        ranked = sorted([quiet, shaken], key=disasters_service._significance, reverse=True)
        assert ranked[0].id == "shaken"

    def test_a_loss_record_competes_on_harm(self) -> None:
        """Loss records carry no magnitude, so harm has to stand in for one."""
        from api.schemas.location import DisasterImpact

        deadly = DisasterEventSchema(
            id="deadly",
            type="flood",
            area_name="Tangerang",
            title="Flood — Tangerang",
            impact=DisasterImpact(deaths=100),
            source="BNPB DIBI (DesInventar)",
            scope="regional",
            distance_meters=19_000.0,
        )
        trivial = DisasterEventSchema(
            id="trivial",
            type="flood",
            area_name="Elsewhere",
            title="Flood — Elsewhere",
            impact=DisasterImpact(deaths=0),
            source="BNPB DIBI (DesInventar)",
            scope="regional",
            distance_meters=1_000.0,
        )
        ranked = sorted([trivial, deadly], key=disasters_service._significance, reverse=True)
        assert ranked[0].id == "deadly"


class TestDisplayGrouping:
    """Rows are grouped by how well their distance is known.

    The figure column says three different kinds of thing — an exact distance, a
    district that contains the coordinate, a lower bound — and interleaving them
    makes a reader re-derive what each number means on every row. Grouping them
    puts the measured figures first, then the rows with no distance at all, then
    the bounds.
    """

    @staticmethod
    def _row(identifier: str, basis: str | None, distance: float, **overrides):
        row = {
            "id": identifier,
            "type": "flood",
            "title": identifier,
            "source": "test",
            "distance_meters": distance,
            "distance_basis": basis,
            "scope": "point" if basis == "measured" else "regional",
        }
        row.update(overrides)
        return DisasterEventSchema(**row)

    def test_the_groups_come_in_order(self) -> None:
        rows = [
            self._row("centre", "area_centre", 63_000.0),
            self._row("bound", "area_edge", 5_900.0),
            self._row("inside", "area_edge", 0.0),
            self._row("measured", "measured", 24_000.0),
        ]

        ordered = sorted(rows, key=disasters_service._display_order)

        assert [row.id for row in ordered] == ["measured", "inside", "bound", "centre"]

    def test_a_far_measured_row_still_leads_a_near_bound(self) -> None:
        """The group decides first, so 24 km measured beats 5.9 km bounded.

        That is the point: the measured figure is a fact about this event, and
        the bound is only the nearest it could have been.
        """
        rows = [
            self._row("bound", "area_edge", 5_900.0),
            self._row("measured", "measured", 24_000.0),
        ]

        ordered = sorted(rows, key=disasters_service._display_order)

        assert [row.id for row in ordered] == ["measured", "bound"]

    def test_the_nearest_leads_inside_a_group(self) -> None:
        """Reading order is distance; severity decides membership, not position.

        A magnitude 5.0 two kilometres away is listed above a magnitude 7.7
        twenty kilometres away. That is deliberate — but only because
        `_significance` still governs *which* events reach the list, so the 7.7
        cannot be dropped for being further out, the way a plain nearest-N cut
        once dropped it.
        """
        rows = [
            self._row("small", "measured", 2_000.0, type="earthquake", magnitude=5.0),
            self._row("big", "measured", 20_000.0, type="earthquake", magnitude=7.7),
        ]

        ordered = sorted(rows, key=disasters_service._display_order)

        assert [row.id for row in ordered] == ["small", "big"]

    def test_the_nearer_of_two_equals_still_wins(self) -> None:
        rows = [
            self._row("far", "area_edge", 20_000.0),
            self._row("near", "area_edge", 6_000.0),
        ]

        ordered = sorted(rows, key=disasters_service._display_order)

        assert [row.id for row in ordered] == ["near", "far"]
