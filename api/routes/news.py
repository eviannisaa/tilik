"""Recent local news for a single point."""

from __future__ import annotations

from fastapi import APIRouter

from api.routes.dependencies import CoordinatePair
from api.schemas.location import LocationInfo, NewsResponse
from api.services import geocoding
from api.services import news as news_service

router = APIRouter(prefix="/location", tags=["news"])


@router.get("/news", response_model=NewsResponse, summary="Recent local news")
async def get_news(coordinates: CoordinatePair) -> NewsResponse:
    latitude, longitude = coordinates

    # News is searched by place name, so this endpoint has to resolve one first.
    # The full report reuses the geocode it already has instead of paying twice.
    location = await geocoding.reverse(latitude, longitude) or LocationInfo(
        latitude=latitude, longitude=longitude
    )
    news, _ = await news_service.get_local_news(location)

    return NewsResponse(latitude=latitude, longitude=longitude, news=news)
