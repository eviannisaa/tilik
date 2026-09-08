"""HTTP routers, one module per topic."""

from api.routes import (
    air_quality,
    disaster,
    elevation,
    hazard,
    health,
    location,
    news,
    places,
    report,
)

__all__ = [
    "air_quality",
    "disaster",
    "elevation",
    "hazard",
    "health",
    "location",
    "news",
    "places",
    "report",
]
