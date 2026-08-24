"""Local-news parsing and topic classification.

The feed itself is fine; every bug in this area has been in what we *ask* for
and what we do with the answer. Both regressions captured here were live
failures, not hypotheticals:

* ``when:12m`` returned an empty feed for every location on earth, because
  Google reads ``m`` as *minutes*. It fails silently — a valid, empty RSS body.
* ``rob`` (tidal flooding) matched inside "roboh" (collapsed), filing a landslide
  story under coastal erosion.
"""

from __future__ import annotations

import pytest

from api.schemas.location import LocationInfo
from api.services.news import build_query, classify, parse_feed, search_area


def _feed(*items: str) -> str:
    body = "".join(items)
    return f'<?xml version="1.0"?><rss version="2.0"><channel>{body}</channel></rss>'


def _item(title: str, *, link: str = "https://example.com/a", date: str | None = None,
          source: str | None = "detikNews") -> str:
    published = f"<pubDate>{date}</pubDate>" if date else ""
    origin = f"<source>{source}</source>" if source else ""
    return f"<item><title>{title}</title><link>{link}</link>{published}{origin}</item>"


class TestQuery:
    def test_window_is_expressed_in_days_not_months(self):
        """`when:12m` means twelve *minutes* — the feed comes back empty."""
        query = build_query("Kota Bandung", 12)
        assert "when:360d" in query
        assert "12m" not in query

    def test_area_is_quoted_as_a_phrase(self):
        """Unquoted, "Tangerang Selatan" returns landslides in Gorontalo."""
        assert build_query("Tangerang Selatan", 6).startswith('"Tangerang Selatan"')


class TestClassify:
    @pytest.mark.parametrize(
        ("title", "expected"),
        [
            ("16 Titik di Tangsel Sempat Banjir Capai 1 Meter", "flood"),
            ("Banjir Bandang Terjang Garut, 3 Orang Hilang", "flashFlood"),
            ("Gempa M 5,2 Guncang Sukabumi", "earthquake"),
            ("Kebakaran Hutan Meluas di Riau", "wildfire"),
            ("Waspada Angin Kencang di Banten", "extremeWeather"),
            ("Abrasi Pantai Ancam Permukiman", "coastalErosion"),
        ],
    )
    def test_reads_indonesian_hazard_terms(self, title, expected):
        assert classify(title)[0] == expected

    def test_ignores_a_headline_with_no_hazard_in_it(self):
        """Google's relevance is loose; the hazard word is what keeps this a
        section about events rather than about the town."""
        assert classify("Rapat Anggaran Pemkot Digelar Hari Ini") is None

    def test_short_terms_do_not_match_inside_longer_words(self):
        """"rob" sits inside "roboh"; this story is a landslide."""
        assert classify("Rumah roboh terdampak longsor di Cikajang")[0] == "landslide"

    def test_leads_with_the_first_hazard_named(self):
        """A story about both is filed under the one it leads with."""
        assert classify("25 Titik Banjir dan 13 Lokasi Longsor")[0] == "flood"
        assert classify("Longsor dan Banjir Melanda Cianjur")[0] == "landslide"

    def test_longest_phrase_wins_a_tie(self):
        """Otherwise "banjir bandang" would read as ordinary flooding."""
        assert classify("Banjir Bandang Garut")[0] == "flashFlood"


class TestParseFeed:
    def test_strips_the_publisher_google_appends_to_every_headline(self):
        items = parse_feed(_feed(_item("Banjir Rendam Tangsel - detikNews")), limit=5)
        assert items[0].title == "Banjir Rendam Tangsel"

    def test_drops_items_that_are_not_about_a_hazard(self):
        feed = _feed(_item("Banjir Rendam Tangsel"), _item("Pelantikan Pejabat Baru"))
        assert len(parse_feed(feed, limit=5)) == 1

    def test_deduplicates_syndicated_headlines(self):
        """The same story runs across outlets under near-identical headlines."""
        feed = _feed(
            _item("Banjir Rendam Tangsel", link="https://a.com/1"),
            _item("Banjir Rendam Tangsel!", link="https://b.com/2"),
        )
        assert len(parse_feed(feed, limit=5)) == 1

    def test_orders_newest_first(self):
        feed = _feed(
            _item("Banjir lama", date="Mon, 05 Jan 2026 07:00:00 GMT"),
            _item("Longsor baru", date="Tue, 04 Aug 2026 07:00:00 GMT"),
        )
        assert [i.title for i in parse_feed(feed, limit=5)] == ["Longsor baru", "Banjir lama"]

    def test_respects_the_limit(self):
        feed = _feed(*(_item(f"Banjir di titik {n}") for n in range(20)))
        assert len(parse_feed(feed, limit=3)) == 3

    def test_survives_a_body_that_is_not_xml(self):
        """A provider answering with an error page must not break the report."""
        assert parse_feed("<html>503 Service Unavailable</html>", limit=5) == []

    def test_skips_items_missing_a_title_or_link(self):
        assert parse_feed(_feed("<item><title>Banjir</title></item>"), limit=5) == []


class TestSearchArea:
    def test_prefers_the_level_indonesian_outlets_report_at(self):
        """Headlines name the kota/kabupaten, not the kelurahan."""
        location = LocationInfo(
            latitude=0, longitude=0, locality="Rawa Buntu",
            district="Serpong", city="Kota Tangerang Selatan", province="Banten",
        )
        assert search_area(location) == "Kota Tangerang Selatan"

    def test_falls_back_through_district_then_province(self):
        assert search_area(LocationInfo(latitude=0, longitude=0, district="Serpong")) == "Serpong"
        assert search_area(LocationInfo(latitude=0, longitude=0, province="Banten")) == "Banten"

    def test_returns_none_when_there_is_no_name_to_search(self):
        assert search_area(LocationInfo(latitude=0, longitude=0)) is None
