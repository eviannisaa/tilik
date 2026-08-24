"""Nearby facilities, from OpenStreetMap via Overpass.

"What's actually around this plot" is one of the most useful things you can know
before buying: how far to a clinic, whether there's a school, is there a market
within walking distance. Overpass answers all of it from OSM in one query.

Categories are defined here rather than in the route so the grouping stays a
data decision, and adding a category is a one-line change.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from api.core.cache import TTLCache
from api.core.config import get_settings
from api.core.errors import TilikError
from api.core.geo import haversine_meters
from api.core.http import fetch_json_from_first
from api.services import overpass
from api.schemas.common import DataSource
from api.schemas.location import NearbyPlace, NearbyPlaces, PlaceCategory

logger = logging.getLogger("tilik.services.places")

PROVIDER = "overpass"


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    #: OSM `amenity` values that belong to this category.
    amenity: tuple[str, ...] = ()
    #: OSM `shop` values that belong to this category.
    shop: tuple[str, ...] = ()
    #: OSM `railway` values (only `station` is useful here).
    railway: tuple[str, ...] = ()


CATEGORIES: tuple[Category, ...] = (
    Category(
        key="health",
        label="Health",
        amenity=("hospital", "clinic", "doctors", "pharmacy"),
    ),
    Category(
        key="education",
        label="Education",
        amenity=("school", "kindergarten", "college", "university"),
    ),
    Category(
        key="shopping",
        label="Shops & markets",
        amenity=("marketplace",),
        shop=("supermarket", "convenience", "mall", "department_store"),
    ),
    Category(
        key="transport",
        label="Transport",
        amenity=("bus_station", "fuel"),
        railway=("station",),
    ),
    Category(
        key="safety",
        label="Safety",
        amenity=("police", "fire_station"),
    ),
    Category(
        key="services",
        label="Services",
        amenity=("bank", "post_office"),
    ),
    Category(
        key="worship",
        label="Places of worship",
        amenity=("place_of_worship",),
    ),
)

#: Reverse lookup from an OSM tag value to the category it belongs to.
_TAG_TO_CATEGORY: dict[tuple[str, str], Category] = {
    (tag_key, value): category
    for category in CATEGORIES
    for tag_key, values in (
        ("amenity", category.amenity),
        ("shop", category.shop),
        ("railway", category.railway),
    )
    for value in values
}

_cache = TTLCache(ttl_seconds=get_settings().cache_ttl_seconds)


def _build_query(latitude: float, longitude: float, radius_meters: int, timeout: int) -> str:
    """One Overpass query covering every category.

    `nwr` catches nodes, ways and relations (a hospital is often a building
    polygon, not a point), and `out center` gives each one a single coordinate.
    """
    clauses: list[str] = []
    around = f"around:{radius_meters},{latitude},{longitude}"

    for tag_key in ("amenity", "shop", "railway"):
        values = sorted(
            {value for (key, value) in _TAG_TO_CATEGORY if key == tag_key},
        )
        if values:
            clauses.append(f'nwr({around})["{tag_key}"~"^({"|".join(values)})$"];')

    return f"[out:json][timeout:{timeout}];({''.join(clauses)});out center tags;"


def _to_place(element: dict, latitude: float, longitude: float) -> NearbyPlace | None:
    tags = element.get("tags") or {}

    # Unnamed facilities are noise in a list a human will read.
    name = tags.get("name")
    if not name:
        return None

    centre = element.get("center") or {"lat": element.get("lat"), "lon": element.get("lon")}
    if centre.get("lat") is None or centre.get("lon") is None:
        return None

    for tag_key in ("amenity", "shop", "railway"):
        value = tags.get(tag_key)
        category = _TAG_TO_CATEGORY.get((tag_key, value)) if value else None
        if category is not None:
            return NearbyPlace(
                name=str(name),
                kind=value,
                category=category.key,
                distance_meters=round(
                    haversine_meters(latitude, longitude, centre["lat"], centre["lon"]), 1
                ),
            )

    return None


def _group(places: list[NearbyPlace], per_category: int) -> list[PlaceCategory]:
    """Bucket places by category, nearest first, keeping the declared order.

    `per_category` of 0 keeps every place found. Anything higher truncates each
    bucket, which the reader has no way of seeing — so it is off by default.
    """
    buckets: dict[str, list[NearbyPlace]] = {category.key: [] for category in CATEGORIES}
    for place in places:
        buckets[place.category].append(place)

    grouped: list[PlaceCategory] = []
    for category in CATEGORIES:
        found = sorted(buckets[category.key], key=lambda place: place.distance_meters)
        if not found:
            continue
        grouped.append(
            PlaceCategory(
                key=category.key,
                label=category.label,
                count=len(found),
                nearest=found[0],
                places=found[:per_category] if per_category else found,
            )
        )
    return grouped


async def get_nearby_places(
    latitude: float, longitude: float
) -> tuple[NearbyPlaces, DataSource]:
    """Facilities around the point, grouped by category."""
    settings = get_settings()
    radius = settings.places_radius_meters

    if not settings.enable_external_apis:
        return (
            NearbyPlaces(
                radius_meters=radius,
                confidence="none",
                note="External APIs are disabled, so nearby places weren't looked up.",
            ),
            DataSource(
                field="places",
                provider="unavailable",
                quality="unavailable",
                note="External APIs are disabled.",
            ),
        )

    cache_key = f"places:{latitude:.4f}:{longitude:.4f}"
    cached = _cache.get(cache_key)
    if cached is None:
        # No longer doubled. The doubling dated from a single Overpass host,
        # where a generous budget cost nothing; with a fallback chain it became
        # the slowest branch of the whole report — 16 seconds against a frontend
        # that gives the report 20. A healthy Overpass answers this query in
        # 2-3s, so 10 is ample, and the chain splits it across its hosts.
        timeout = max(10, int(settings.external_timeout_seconds))
        try:
            # Every mirror in turn. The main host answers 504 when its shared
            # queue is full and refuses connections outright once it has
            # rate-limited an address — and without a fallback a single
            # transient failure emptied the whole section.
            payload, host_index = await fetch_json_from_first(
                settings.overpass_urls,
                provider=PROVIDER,
                method="POST",
                data=_build_query(latitude, longitude, radius, timeout),
                headers={"Content-Type": "text/plain; charset=utf-8"},
                timeout=float(timeout),
            )
        except TilikError as exc:
            logger.warning("Nearby places degraded: %s", exc)
            return (
                NearbyPlaces(
                    radius_meters=radius,
                    confidence="none",
                    note="OpenStreetMap didn't answer, so we couldn't list what's nearby.",
                ),
                DataSource(
                    field="places",
                    provider=PROVIDER,
                    quality="unavailable",
                    note="Overpass did not answer in time.",
                ),
            )

        # Raises when Overpass reports a runtime error inside a 200, which it
        # does under load. See `api.services.overpass`.
        elements = overpass.elements_of(
            payload, provider=PROVIDER, trust_empty=host_index == 0
        )
        found = [_to_place(element, latitude, longitude) for element in elements]
        cached = [place for place in found if place is not None]
        _cache.set(cache_key, cached)

    categories = _group(cached, settings.places_per_category)

    return (
        NearbyPlaces(
            radius_meters=radius,
            total=len(cached),
            categories=categories,
            confidence="high" if categories else "low",
            note=(
                None
                if categories
                else f"Nothing mapped in OpenStreetMap within {radius} m of this point."
            ),
        ),
        DataSource(field="places", provider=PROVIDER, quality="live"),
    )
