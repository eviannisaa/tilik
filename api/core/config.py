"""Application settings, sourced from environment variables.

Every external dependency is configurable so a provider can be swapped without
touching service code. The defaults all point at free, key-less endpoints, so a
fresh clone works with an empty `.env`.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Tilik API"
    version: str = "0.1.0"
    environment: str = Field(default="development")

    # --- Database (optional) -------------------------------------------------
    # Without it the API still answers; spatial lookups just fall back to
    # external providers or report themselves as unavailable.
    database_url: str | None = None
    database_pool_size: int = 3
    database_connect_timeout: float = 8.0

    # --- Geocoding -----------------------------------------------------------
    nominatim_base_url: str = "https://nominatim.openstreetmap.org"
    # Nominatim's usage policy requires a real, identifying User-Agent.
    nominatim_user_agent: str = "tilik/0.1 (+https://github.com/your-org/tilik)"
    nominatim_email: str | None = None

    # --- Elevation -----------------------------------------------------------
    # Primary source: OpenTopography's Global DEM API. It needs a free API key
    # (portal.opentopography.org → request an API key). Without one we fall
    # straight through to the key-less endpoint below.
    opentopography_api_url: str = "https://portal.opentopography.org/API/globaldem"
    opentopography_api_key: str | None = None
    #: SRTMGL1 = 30 m global. SRTMGL3 (90 m) is lighter; NASADEM is an option.
    opentopography_dem_type: str = "SRTMGL1"

    # Fallback: any endpoint returning {"results": [{"elevation": ...}]}
    # (OpenTopoData, Open-Elevation, or your own tile server).
    elevation_api_url: str = "https://api.opentopodata.org/v1/srtm30m"

    # --- Disasters -----------------------------------------------------------
    earthquake_api_url: str = "https://earthquake.usgs.gov/fdsnws/event/1/query"
    # Optional GeoJSON feed (e.g. a BNPB export). Unset = skipped.
    disaster_api_url: str | None = None
    #: NOAA/NCEI historical tsunami database. The *runups* table, not `events`:
    #: a runup is a measured place the wave reached, while an event carries only
    #: the source coordinate — which for the 2004 tsunami sits 250 km off Aceh.
    ncei_tsunami_api_url: str = (
        "https://www.ngdc.noaa.gov/hazel/hazard-service/api/v1/tsunamis/runups"
    )
    disaster_radius_meters: int = 50_000
    #: Search radius for earthquakes. Unset follows `disaster_radius_meters`,
    #: which is the configured behaviour: one radius for every hazard.
    #:
    #: Worth knowing before setting it. Epicentre distance is a poor ruler for
    #: an earthquake: the M7.5 that destroyed Palu in 2018 has its epicentre
    #: 71.6 km from the city and shook it at MMI 8.4 with 40 felt reports, so
    #: inside 25 km it is not returned at all while an M4.6 five kilometres away
    #: that nobody noticed is. Widening this brings such events in, and the felt
    #: filter rather than the radius is what keeps that from becoming noise —
    #: `disaster_max_depth_km` and the intensity checks drop events that reached
    #: the surface as nothing, at any distance.
    earthquake_radius_meters: int | None = None

    # GDACS is no longer part of the disaster history: its coordinates are
    # centroids of affected regions and it publishes no casualty figures. These
    # keys serve `scripts/import_gdacs.py` alone, for anyone who wants it back.
    gdacs_api_url: str = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
    gdacs_alert_levels: str = "Green;Orange;Red"
    #: Restrict the feed to one country, or blank for worldwide.
    gdacs_country: str = "Indonesia"
    #: Wider than `disaster_radius_meters` on purpose: GDACS coordinates are
    #: centroids of affected regions, so a flood 80 km away may well be the same
    #: event that reached this area.
    gdacs_radius_meters: int = 150_000
    disaster_years: int = 25
    #: How far back to read tsunamis. Unset follows `disaster_years`, which is
    #: the configured behaviour: one window for every hazard.
    #:
    #: Worth knowing before setting it. Tsunamis recur over centuries, not
    #: years, so a 25-year window reports "no tsunami" for the west Java coast
    #: Krakatoa flooded in 1883 and for every stretch of Sumatra hit before
    #: 2001. NOAA/NCEI's Indonesian record runs to the 1600s.
    tsunami_years: int | None = None
    #: Show only events whose coordinate is a measured location.
    #:
    #: A disaster history mixes two very different kinds of record. A seismic
    #: epicentre is a measured point, so its distance from a pin is a real
    #: figure. BNPB's DIBI records carry no coordinate at all — every
    #: `latitude`/`longitude` in the export is literally 0 — so they are placed
    #: at their district's centre, and GDACS uses the centroid of an affected
    #: region. For those, "18 km" means "that area's middle is 18 km away", not
    #: "the event was 18 km away".
    #:
    #: Turning this on keeps only the measured ones, so every distance in the
    #: section is a true distance from the checked coordinate. The cost is
    #: severe and worth knowing: it excludes the entire DIBI archive — 32,447
    #: records, every flood, landslide, windstorm, drought and wildfire — which
    #: leaves earthquakes alone, and earthquakes are not the hazard that
    #: actually recurs in most of Java.
    disaster_require_measured_location: bool = False
    disaster_min_magnitude: float = 4.5
    #: Depth cutoff for earthquakes the catalogue gives no intensity or felt
    #: report for. Java sits above a subducting slab that produces a steady
    #: stream of magnitude 4–5 events at 130–190 km, which reach the surface as
    #: nothing — listing them as "disaster history" for a plot of land is noise.
    #: Events with real intensity or felt evidence are kept at any depth. Raise
    #: this well past 700 to disable the cutoff.
    disaster_max_depth_km: float = 70.0
    #: Nearest N events guaranteed per hazard type, so a busy seismic record
    #: can't crowd floods and eruptions out of the list.
    disaster_events_per_type: int = 3

    # --- Hazard indices (BNPB InaRISK) ---------------------------------------
    # ArcGIS ImageServers returning a 0..1 hazard index per pixel. This is the
    # authoritative Indonesian flood/landslide/quake/tsunami hazard source.
    inarisk_base_url: str = "https://gis.bnpb.go.id/server/rest/services/inarisk"
    #: Some InaRISK layers (tsunami, coastal abrasion) are modelled as a thin
    #: band along the shoreline, so sampling a single pixel misses them for any
    #: point a few hundred metres inland. Hazards are looked up across a
    #: neighbourhood of this radius instead, reporting how far away the value was
    #: found. 0 restores exact-point behaviour.
    inarisk_neighbourhood_meters: int = 500
    #: BNPB's server is slower and flakier than the other providers. All five
    #: hazard layers are queried concurrently, so this is roughly the worst-case
    #: contribution of InaRISK to a report — raise it if you'd rather wait.
    inarisk_timeout_seconds: float = 8.0

    # --- Local news ----------------------------------------------------------
    # Google News RSS: free, no key, and — unlike GDELT, which rate-limits to
    # one request every 5 seconds — usable from a serverless function. It reads
    # Indonesian sources (detik, Kompas, ANTARA, BPBD and pemkot newsrooms),
    # which is where flood and landslide reporting actually lives.
    google_news_rss_url: str = "https://news.google.com/rss/search"
    #: Feed language/edition. `id`/`ID` gets Indonesian-language local reporting.
    news_language: str = "id"
    news_country: str = "ID"
    #: How far back to search. Google accepts this as a `when:` query operator.
    news_months: int = 12
    #: Cap on stories returned, newest first, after relevance filtering.
    news_max_items: int = 12
    #: Turn off to drop the news section without disabling every other provider.
    enable_news: bool = True

    # --- Geographic features -------------------------------------------------
    overpass_api_url: str = "https://overpass-api.de/api/interpreter"
    #: Mirrors to fall back to, in order, when the main host will not answer.
    #:
    #: Overpass's public instance is shared and rate-limits by address: once it
    #: does, it stops accepting connections altogether and no retry helps. The
    #: mirrors fail independently, so a list survives what one host cannot.
    #:
    #: Each entry receives the checked coordinate, because that is what the query
    #: contains, so this is also a list of who gets to see it. Where a coordinate
    #: is sent is the operator's call, which is why the list is short and
    #: configurable rather than exhaustive. Comma-separated; blank disables the
    #: fallback.
    #:
    #: Chosen by measurement, and the measurement that mattered was coverage.
    #: Across seven known hosts: the main host answered in 3.0s, `osm.ch` in
    #: 0.9s, `maps.mail.ru` in 8.8s, `private.coffee` gave a 502, and
    #: `kumi.systems`, `openstreetmap.ru` and `osm.jp` refused or timed out.
    #:
    #: `osm.ch` was the fastest and is disqualified anyway: it holds Switzerland
    #: only. Asked about Serpong it answers 200 with zero elements, which is not
    #: an error and so was reported as "nothing mapped around this point" for a
    #: plot with 120 places nearby. A mirror that lies quietly is worse than one
    #: that fails. `maps.mail.ru` carries the whole planet — verified: 32
    #: elements where `osm.ch` returned none — and is hosted in Russia, which is
    #: worth knowing given the query carries the coordinate. Remove it if that
    #: matters more than the fallback does.
    overpass_fallback_urls: str = (
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
    )
    waterway_radius_meters: int = 2_000
    #: Radius for the "what's around here" lookup (hospitals, schools, shops…).
    places_radius_meters: int = 1_500
    #: Cap on how many places to return per category, nearest first.
    #: Cap on places listed per category. 0 lists every one found.
    #:
    #: Truncating here was silent from the reader's side and the count that
    #: hinted at it — "×6" beside a distance — read as arithmetic and was
    #: removed. Two plots then looked alike while one had five clinics inside
    #: 1.5 km and the other fourteen, which is exactly the difference the
    #: section exists to show. Raise the cap only if a dense city centre makes
    #: the list unwieldy, and know that doing so hides places again.
    places_per_category: int = 0

    # --- Behaviour -----------------------------------------------------------
    external_timeout_seconds: float = 8.0
    #: Turn off to run fully offline against clearly-labelled sample data.
    enable_external_apis: bool = True
    cache_ttl_seconds: int = 900
    rate_limit_per_minute: int = 60
    #: Comma-separated origins, or "*" while the API is same-origin only.
    cors_allow_origins: str = "*"

    @field_validator("database_url")
    @classmethod
    def _normalise_database_url(cls, value: str | None) -> str | None:
        """Accept the plain `postgres://` URLs that Supabase and Heroku hand out."""
        if not value:
            return None
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+asyncpg://" + value[len(prefix) :]
        return value

    @property
    def overpass_urls(self) -> list[str]:
        """The main host first, then each configured mirror."""
        mirrors = [url.strip() for url in self.overpass_fallback_urls.split(",") if url.strip()]
        return [self.overpass_api_url, *mirrors]

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached so every module shares one parsed copy per process."""
    return Settings()
