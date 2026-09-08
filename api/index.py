"""FastAPI entry point.

This module only wires things together — routing, middleware and lifecycle.
All behaviour lives in `api/routes` and `api/services`.

Vercel imports the module-level ``app`` from here (see `vercel.json`).
Locally: ``uvicorn api.index:app --reload --port 8000``.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.core.config import get_settings
from api.core.errors import register_exception_handlers
from api.core.http import close_client, install_log_redaction
from api.core.ratelimit import RateLimitMiddleware
from api.db import dispose_engine
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

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
# httpx logs every request URL at INFO, and two providers authenticate by
# query string. Without this the token is in the log.
install_log_redaction()

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    # Serverless may reuse the process, but a clean shutdown matters locally.
    await close_client()
    await dispose_engine()


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description=(
        "Location context for land and property decisions: terrain, flood risk, "
        "disaster history and nearby geography. Informational only."
    ),
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)

app.add_middleware(RateLimitMiddleware, requests_per_minute=settings.rate_limit_per_minute)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

register_exception_handlers(app)

# Every route is namespaced under /api so the frontend and API can share a domain.
app.include_router(health.router, prefix="/api")
app.include_router(location.router, prefix="/api")
app.include_router(elevation.router, prefix="/api")
app.include_router(disaster.router, prefix="/api")
app.include_router(hazard.router, prefix="/api")
app.include_router(news.router, prefix="/api")
app.include_router(air_quality.router, prefix="/api")
app.include_router(places.router, prefix="/api")
app.include_router(report.router, prefix="/api")
