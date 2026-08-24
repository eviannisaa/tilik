"""Async engine/session management.

The database is optional. `get_engine()` returns ``None`` when DATABASE_URL is
unset, and every caller is expected to cope with that rather than fail.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool
from sqlalchemy.sql import text

from api.core.config import get_settings

logger = logging.getLogger("tilik.db")

DatabaseStatus = Literal["connected", "not_configured", "unavailable"]

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine | None:
    """Lazily build the engine; ``None`` means "no database configured"."""
    global _engine, _session_factory

    settings = get_settings()
    if not settings.database_url:
        return None

    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            # Serverless functions are short-lived and often sit behind a
            # connection pooler (Supabase/pgbouncer), where a client-side pool
            # and prepared statements both cause trouble.
            poolclass=NullPool,
            connect_args={
                "timeout": settings.database_connect_timeout,
                "prepared_statement_cache_size": 0,
            },
            future=True,
        )
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)

    return _engine


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession | None]:
    """Yield a session, or ``None`` if the database isn't available.

    Connection failures are swallowed here on purpose: a missing database
    degrades the report, it doesn't break the request.
    """
    if get_engine() is None or _session_factory is None:
        yield None
        return

    session: AsyncSession | None = None
    try:
        session = _session_factory()
        yield session
    except Exception as exc:  # noqa: BLE001 - deliberate: degrade, don't fail
        logger.warning("Database session failed: %s", exc)
        yield None
    finally:
        if session is not None:
            await session.close()


async def database_status() -> DatabaseStatus:
    """Used by /api/health to report reachability without raising."""
    engine = get_engine()
    if engine is None:
        return "not_configured"
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return "connected"
    except Exception as exc:  # noqa: BLE001
        logger.warning("Database health check failed: %s", exc)
        return "unavailable"


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
