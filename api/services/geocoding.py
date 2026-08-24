"""Place lookup.

Nominatim is the default provider; swapping it means changing this module and
`NOMINATIM_BASE_URL`, nothing else. When the provider is unreachable we fall
back to a small built-in gazetteer so the app stays usable offline.
"""

from __future__ import annotations

import logging
from typing import Any

from api.core.cache import TTLCache
from api.core.config import get_settings
from api.core.errors import InvalidQueryError, TilikError
from api.core.geo import parse_coordinate_pair
from api.core.http import fetch_json
from api.schemas.location import LocationInfo, SearchResult

logger = logging.getLogger("tilik.services.geocoding")

PROVIDER = "nominatim"

_cache = TTLCache(ttl_seconds=get_settings().cache_ttl_seconds)

#: Minimal offline gazetteer — enough to demo the flow without any network.
FALLBACK_PLACES: list[dict[str, Any]] = [
    {"name": "Jakarta", "lat": -6.2088, "lng": 106.8456, "region": "DKI Jakarta"},
    {"name": "Bandung", "lat": -6.9175, "lng": 107.6191, "region": "Jawa Barat"},
    {"name": "Bogor", "lat": -6.5950, "lng": 106.8166, "region": "Jawa Barat"},
    {"name": "Bekasi", "lat": -6.2383, "lng": 106.9756, "region": "Jawa Barat"},
    {"name": "Semarang", "lat": -6.9932, "lng": 110.4203, "region": "Jawa Tengah"},
    {"name": "Yogyakarta", "lat": -7.7956, "lng": 110.3695, "region": "DI Yogyakarta"},
    {"name": "Surabaya", "lat": -7.2575, "lng": 112.7521, "region": "Jawa Timur"},
    {"name": "Malang", "lat": -7.9666, "lng": 112.6326, "region": "Jawa Timur"},
    {"name": "Denpasar", "lat": -8.6705, "lng": 115.2126, "region": "Bali"},
    {"name": "Medan", "lat": 3.5952, "lng": 98.6722, "region": "Sumatera Utara"},
    {"name": "Palembang", "lat": -2.9761, "lng": 104.7754, "region": "Sumatera Selatan"},
    {"name": "Padang", "lat": -0.9471, "lng": 100.4172, "region": "Sumatera Barat"},
    {"name": "Makassar", "lat": -5.1477, "lng": 119.4327, "region": "Sulawesi Selatan"},
    {"name": "Manado", "lat": 1.4748, "lng": 124.8421, "region": "Sulawesi Utara"},
    {"name": "Balikpapan", "lat": -1.2379, "lng": 116.8529, "region": "Kalimantan Timur"},
    {"name": "Pontianak", "lat": -0.0263, "lng": 109.3425, "region": "Kalimantan Barat"},
]


def _headers() -> dict[str, str]:
    settings = get_settings()
    headers = {"User-Agent": settings.nominatim_user_agent}
    if settings.nominatim_email:
        headers["From"] = settings.nominatim_email
    return headers


def _search_fallback(query: str, limit: int) -> list[SearchResult]:
    term = query.strip().lower()
    matches = [place for place in FALLBACK_PLACES if term in place["name"].lower()]
    return [
        SearchResult(
            latitude=place["lat"],
            longitude=place["lng"],
            name=place["name"],
            display_name=f"{place['name']}, {place['region']}, Indonesia",
            category="place",
        )
        for place in matches[:limit]
    ]


#: Detail level for reverse geocoding — Nominatim's own default.
#:
#: This was 14, which looked like a sensible "neighbourhood" level and was wrong:
#: at that zoom Nominatim matches the largest polygon containing the point, so a
#: plot inside the BSD City relation reported *Pagedangan, Kabupaten Tangerang*
#: — the relation's own hierarchy — when the point is actually in Serpong, Kota
#: Tangerang Selatan. Naming the wrong regency is worse than being vague: it's a
#: different local government with different rules.
REVERSE_ZOOM = 18

#: Address keys that name an administrative area, at any level.
#:
#: Which key holds which level is not consistent in Indonesia — the kecamatan
#: arrives as `municipality` in Tangerang and `district` in Bandung, the
#: kabupaten as `county` in one place and `city` in another, and for Jakarta the
#: province turns up under `city` with no `state` at all. So the key names are
#: only used to decide what counts as an administrative name; the hierarchy
#: comes from the order Nominatim returns them in, which is most specific first.
ADMIN_KEYS = frozenset(
    {
        "neighbourhood",
        "quarter",
        "hamlet",
        "village",
        "suburb",
        "town",
        "municipality",
        "subdistrict",
        "district",
        "city_district",
        "city",
        "county",
        "state_district",
        "province",
        "region",
        "state",
    }
)


def admin_levels(address: dict[str, Any]) -> list[str]:
    """Administrative names for a place, most specific first.

    Duplicates are dropped: a kecamatan is commonly repeated under two keys, and
    printing "Pagedangan, Pagedangan" is worse than picking one.
    """
    seen: set[str] = set()
    levels: list[str] = []

    for key, value in address.items():
        if key not in ADMIN_KEYS or not value:
            continue
        text = str(value).strip()
        if not text or text.casefold() in seen:
            continue
        seen.add(text.casefold())
        levels.append(text)

    return levels


def _at(levels: list[str], from_end: int) -> str | None:
    """Read a level counting back from the largest, or ``None`` if absent."""
    return levels[-from_end] if len(levels) >= from_end else None


def admin_fields(address: dict[str, Any]) -> dict[str, str | None]:
    """Kecamatan, kabupaten or kota, and province, from a Nominatim address.

    Positional rather than by key name: the levels arrive ordered smallest to
    largest, so counting back from the end gives province, then kabupaten/kota,
    then kecamatan, whatever keys they happened to come under. The kecamatan
    arrives as `municipality` in Tangerang and `district` in Bandung, and for
    Jakarta the province turns up under `city` with no `state` at all.

    Shared with `_to_search_result`, which had none of this. `search` asks
    Nominatim for `addressdetails` and then ignored the address it got back, so a
    place picked from the search box carried a name and nothing else, and the
    administrative line under it stayed empty until something else happened to
    trigger a reverse lookup.
    """
    levels = admin_levels(address)
    return {
        "district": _at(levels, 3),
        "city": _at(levels, 2),
        "province": address.get("state") or address.get("region") or _at(levels, 1),
    }


def _short_name(payload: dict[str, Any]) -> str:
    """Nominatim's `name` is often empty; fall back to the first address part."""
    if payload.get("name"):
        return str(payload["name"])
    address = payload.get("address") or {}
    for key in ("village", "suburb", "neighbourhood", "town", "city_district", "city", "county"):
        if address.get(key):
            return str(address[key])
    display = str(payload.get("display_name", ""))
    return display.split(",")[0] if display else "Unnamed place"


def _to_search_result(payload: dict[str, Any]) -> SearchResult | None:
    try:
        latitude = float(payload["lat"])
        longitude = float(payload["lon"])
    except (KeyError, TypeError, ValueError):
        return None

    bbox = payload.get("boundingbox")
    bounding_box = None
    if isinstance(bbox, list) and len(bbox) == 4:
        try:
            bounding_box = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
        except (TypeError, ValueError):
            bounding_box = None

    return SearchResult(
        latitude=latitude,
        longitude=longitude,
        name=_short_name(payload),
        display_name=str(payload.get("display_name", "")),
        category=payload.get("type") or payload.get("category"),
        bounding_box=bounding_box,
        **admin_fields(payload.get("address") or {}),
    )


async def search(query: str, limit: int = 6) -> tuple[list[SearchResult], str, bool]:
    """Look up places by name.

    Returns ``(results, provider, degraded)`` — `degraded` means the results
    came from the offline gazetteer rather than a live geocoder.
    """
    query = query.strip()
    if not query:
        raise InvalidQueryError("Type at least a couple of characters to search.")
    if len(query) > 200:
        raise InvalidQueryError("That search query is too long.")

    # Pasted coordinates are a location, not a search term.
    pair = parse_coordinate_pair(query)
    if pair is not None:
        latitude, longitude = pair
        return (
            [
                SearchResult(
                    latitude=latitude,
                    longitude=longitude,
                    name=f"{latitude:.5f}, {longitude:.5f}",
                    display_name="Coordinates you entered",
                    category="coordinates",
                )
            ],
            "coordinates",
            False,
        )

    settings = get_settings()
    if not settings.enable_external_apis:
        return _search_fallback(query, limit), "offline-gazetteer", True

    cache_key = f"search:{query.lower()}:{limit}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached, PROVIDER, False

    try:
        payload = await fetch_json(
            f"{settings.nominatim_base_url.rstrip('/')}/search",
            provider=PROVIDER,
            params={
                "q": query,
                "format": "jsonv2",
                "addressdetails": 1,
                "limit": limit,
            },
            headers=_headers(),
        )
    except TilikError as exc:
        logger.warning("Geocoding search degraded: %s", exc)
        return _search_fallback(query, limit), "offline-gazetteer", True

    results = [result for result in map(_to_search_result, payload or []) if result is not None]
    _cache.set(cache_key, results)
    return results, PROVIDER, False


async def reverse(latitude: float, longitude: float) -> LocationInfo | None:
    """Resolve coordinates to a human-readable place. ``None`` when unknown."""
    settings = get_settings()
    if not settings.enable_external_apis:
        return None

    cache_key = f"reverse:{latitude:.4f}:{longitude:.4f}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        payload = await fetch_json(
            f"{settings.nominatim_base_url.rstrip('/')}/reverse",
            provider=PROVIDER,
            params={
                "lat": latitude,
                "lon": longitude,
                "format": "jsonv2",
                "addressdetails": 1,
                "zoom": REVERSE_ZOOM,
            },
            headers=_headers(),
        )
    except TilikError as exc:
        logger.warning("Reverse geocoding degraded: %s", exc)
        return None

    if not isinstance(payload, dict) or payload.get("error"):
        return None

    address = payload.get("address") or {}
    levels = admin_levels(address)

    info = LocationInfo(
        latitude=latitude,
        longitude=longitude,
        name=_short_name(payload),
        display_name=payload.get("display_name"),
        locality=_at(levels, 4) or (levels[0] if levels else None),
        country=address.get("country"),
        postcode=address.get("postcode"),
        # Derived once, in `admin_fields`, so the search box and a dropped pin
        # cannot disagree about which kecamatan a point is in.
        **admin_fields(address),
    )

    _cache.set(cache_key, info)
    return info
