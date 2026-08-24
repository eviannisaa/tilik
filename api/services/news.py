"""Recent news about what has actually happened near a location.

The rest of the report is modelled or catalogued: InaRISK says what *could*
happen, USGS and GDACS say what was *recorded*. Neither picks up the ordinary
local events people care about when they're about to buy a plot — the street
that floods every rainy season, the retaining wall that gave way last March.
That reporting exists, in Indonesian, on detik/Kompas/ANTARA and on BPBD and
pemkot newsrooms. This module reads it.

Source choice: **Google News RSS**. It needs no key, answers in ~1s, and the
`hl=id&gl=ID` edition surfaces exactly those local outlets. GDELT's DOC API was
the obvious alternative and was rejected after testing — it rate-limits to one
request every five seconds per IP, which a serverless function sharing an egress
address cannot honour, and its GEO endpoint is gone (404).

Two things shape the design:

* **This is press coverage, not a hazard record.** A story is evidence that
  something was reported near a *place name*, not at a coordinate. So the
  matched area travels with the results and the UI says which name was searched.
* **One request, not one per hazard.** Google accepts an OR-group, so all eleven
  hazard topics are asked for together. Querying per topic would be eleven round
  trips for the same answer.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ElementTree
from email.utils import parsedate_to_datetime

from api.core.cache import TTLCache
from api.core.config import get_settings
from api.core.errors import TilikError
from api.core.http import fetch_text
from api.schemas.common import DataSource
from api.schemas.location import LocalNews, LocationInfo, NewsItem
from api.services.inarisk import HAZARD_LABELS

logger = logging.getLogger("tilik.services.news")

PROVIDER = "google-news"

#: Search terms per hazard, keyed to match :data:`api.services.inarisk.HAZARD_LABELS`
#: so a story sits under the same name as the hazard-index row it relates to.
#: Indonesian first — that's what the local press writes — with the English term
#: kept for outlets that publish in it.
TOPIC_TERMS: dict[str, tuple[str, ...]] = {
    "flood": ("banjir", "tergenang", "genangan", "luapan", "banjir rob", "flood"),
    "flashFlood": ("banjir bandang", "flash flood"),
    "landslide": ("longsor", "tanah bergerak", "landslide"),
    "earthquake": ("gempa", "gempa bumi", "earthquake"),
    "liquefaction": ("likuefaksi", "liquefaction"),
    "tsunami": ("tsunami",),
    # Bare "rob" is deliberately absent: it is three letters that sit inside
    # ordinary words ("roboh" — collapsed). Tidal flooding is covered by the
    # "banjir rob" phrase under flood instead.
    "coastalErosion": ("abrasi", "gelombang tinggi", "gelombang ekstrem", "coastal erosion"),
    "volcanic": ("erupsi", "letusan", "awan panas", "lahar", "eruption"),
    "extremeWeather": (
        "angin kencang",
        "puting beliung",
        "cuaca ekstrem",
        "hujan lebat",
        "hujan deras",
        "pohon tumbang",
    ),
    "drought": ("kekeringan", "krisis air", "drought"),
    "wildfire": ("kebakaran", "karhutla", "wildfire"),
}

#: Terms that go into the search query. Multi-word phrases are quoted so Google
#: keeps them together; single words are cheaper unquoted.
_QUERY_TERMS: tuple[str, ...] = (
    "banjir",
    "longsor",
    "gempa",
    "tsunami",
    "erupsi",
    "kebakaran",
    "kekeringan",
    "abrasi",
    "likuefaksi",
    '"angin kencang"',
    '"puting beliung"',
    '"cuaca ekstrem"',
)

#: Longest phrases first, so "banjir bandang" is not swallowed by "banjir" and
#: "banjir rob" doesn't classify as plain flooding.
_MATCHERS: tuple[tuple[str, str, re.Pattern[str]], ...] = tuple(
    sorted(
        (
            (topic, term, re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE))
            for topic, terms in TOPIC_TERMS.items()
            for term in terms
        ),
        key=lambda entry: len(entry[1]),
        reverse=True,
    )
)

#: Google appends " - Publisher" to every headline; it's redundant next to the
#: source line the UI already shows.
_SOURCE_SUFFIX = re.compile(r"\s+-\s+[^-]{2,40}$")

_cache = TTLCache(ttl_seconds=get_settings().cache_ttl_seconds)


#: Google's `when:` window has to be given in days. Its `m` unit means *minutes*,
#: not months — `when:12m` silently returns the last twelve minutes of news, which
#: is an empty feed rather than an error.
DAYS_PER_MONTH = 30


def build_query(area: str, months: int) -> str:
    """A single query covering every hazard topic for one place.

    The area is quoted so Google treats it as a phrase — unquoted, a search for
    Tangerang Selatan returns landslides in Gorontalo.
    """
    window = max(1, months) * DAYS_PER_MONTH
    return f'"{area}" ({" OR ".join(_QUERY_TERMS)}) when:{window}d'


def classify(title: str) -> tuple[str, str] | None:
    """Match a headline to a hazard topic, or ``None`` if it isn't about one.

    Google's relevance is loose — a query for floods returns budget meetings
    that mention flooding. Requiring a hazard word in the headline is what keeps
    this section about events rather than about the town in general.
    """
    best: tuple[int, int, str] | None = None
    for topic, term, pattern in _MATCHERS:
        match = pattern.search(title)
        if match is None:
            continue
        # A headline naming two hazards ("Banjir dan Longsor") is filed under
        # the one it leads with; the longest term wins only a genuine tie, which
        # is what keeps "banjir bandang" from reading as plain "banjir".
        candidate = (match.start(), -len(term), topic)
        if best is None or candidate < best:
            best = candidate
    if best is None:
        return None
    return best[2], HAZARD_LABELS[best[2]]


def _clean_title(raw: str) -> str:
    return _SOURCE_SUFFIX.sub("", raw.strip()).strip()


def _published(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).isoformat()
    except (TypeError, ValueError):
        return None


#: Administrative prefixes headlines drop — a story says "Tangerang Selatan",
#: never "Kota Tangerang Selatan".
_AREA_PREFIX = re.compile(r"^(kota|kabupaten|kab\.?|provinsi)\s+", re.IGNORECASE)


def names_area(title: str, area: str | None) -> bool:
    """Whether a headline names the searched area itself.

    A query for Surabaya also returns national wires that merely mention it, so
    this is a ranking signal, not a filter — dropping them would also drop the
    local story whose headline says "di Simo Gunung" and nothing more.
    """
    if not area:
        return False
    bare = _AREA_PREFIX.sub("", area).strip().casefold()
    return bool(bare) and bare in title.casefold()


def parse_feed(xml: str, *, limit: int, area: str | None = None) -> list[NewsItem]:
    """Turn an RSS body into topic-tagged items, newest first.

    Kept separate from the fetch so the parsing rules are testable without a
    network call.
    """
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        logger.warning("News feed was not valid XML: %s", exc)
        return []

    items: list[NewsItem] = []
    seen: set[str] = set()

    for element in root.findall(".//item"):
        title = _clean_title(element.findtext("title") or "")
        url = (element.findtext("link") or "").strip()
        if not title or not url:
            continue

        topic = classify(title)
        if topic is None:
            continue

        # The same story is syndicated across outlets under near-identical
        # headlines; one per headline is enough.
        key = re.sub(r"\W+", "", title.casefold())
        if key in seen:
            continue
        seen.add(key)

        source = element.findtext("source")
        items.append(
            NewsItem(
                id=(element.findtext("guid") or url)[:120],
                title=title,
                url=url,
                published_at=_published(element.findtext("pubDate")),
                source=(source or "").strip() or None,
                topic=topic[0],
                topic_label=topic[1],
            )
        )

    # Local first, then newest. A regional story from this morning is less use
    # than one about this town from last week.
    items.sort(
        key=lambda item: (names_area(item.title, area), item.published_at or ""),
        reverse=True,
    )
    return items[:limit]


def search_area(location: LocationInfo) -> str | None:
    """Pick the place name to search on.

    City (kota/kabupaten) is the level Indonesian outlets actually report at.
    A kelurahan is too fine to be named in a headline; a province is so coarse
    the results stop being about this location at all — but both beat having
    nothing to search.
    """
    for candidate in (location.city, location.district, location.province):
        name = (candidate or "").strip()
        if name:
            return name
    return None


def _unavailable(note: str, *, status: str = "unavailable") -> tuple[LocalNews, DataSource]:
    settings = get_settings()
    return (
        LocalNews(
            months_searched=settings.news_months,
            status=status,  # type: ignore[arg-type]
            note=note,
        ),
        DataSource(field="news", provider=PROVIDER, quality="unavailable", note=note),
    )


async def get_local_news(location: LocationInfo) -> tuple[LocalNews, DataSource]:
    """Recent local reporting for the area a point falls in.

    Never raises: a news section is the most expendable part of the report, so
    any failure degrades to an empty, explained section rather than costing the
    reader everything else.
    """
    settings = get_settings()

    if not settings.enable_news:
        return _unavailable("Local news is turned off for this deployment.")

    if not settings.enable_external_apis:
        return _unavailable("External APIs are disabled, so news wasn't looked up.")

    area = search_area(location)
    if area is None:
        return _unavailable(
            "We couldn't resolve a place name here, and news can only be searched by name.",
            status="no_area",
        )

    cache_key = f"news:{area.casefold()}"
    cached = _cache.get(cache_key)
    if cached is None:
        try:
            body = await fetch_text(
                settings.google_news_rss_url,
                provider=PROVIDER,
                params={
                    "q": build_query(area, settings.news_months),
                    "hl": settings.news_language,
                    "gl": settings.news_country,
                    "ceid": f"{settings.news_country}:{settings.news_language}",
                },
            )
        except TilikError as exc:
            logger.warning("Local news degraded for %s: %s", area, exc)
            return _unavailable(
                f"The news feed didn't answer, so recent reports for {area} are missing."
            )

        cached = parse_feed(body, limit=settings.news_max_items, area=area)
        _cache.set(cache_key, cached)

    if not cached:
        return (
            LocalNews(
                matched_area=area,
                months_searched=settings.news_months,
                status="no_results",
                note=f"No hazard reporting for {area} in the last {settings.news_months} months.",
            ),
            DataSource(
                field="news",
                provider=PROVIDER,
                quality="live",
                note="The feed answered with no matching stories.",
            ),
        )

    topics: list[str] = []
    for item in cached:
        if item.topic not in topics:
            topics.append(item.topic)

    return (
        LocalNews(
            items=cached,
            matched_area=area,
            months_searched=settings.news_months,
            status="ok",
            topics=topics,
        ),
        DataSource(field="news", provider=PROVIDER, quality="live"),
    )
