"""Shared HTTP plumbing for outbound provider calls.

Every external request goes through :func:`fetch_json`, so timeouts, rate-limit
responses and connection failures map onto Tilik's error types in exactly one
place.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from api.core.config import get_settings
from api.core.errors import (
    UpstreamRateLimitedError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)

logger = logging.getLogger("tilik.http")

_client: httpx.AsyncClient | None = None
_client_lock = asyncio.Lock()

#: Providers that ask for a minimum gap between calls (seconds).
#: Nominatim's usage policy requires ~1 req/s. BNPB's GIS server starts
#: refusing connections under bursts, so we stagger those too.
_MIN_INTERVAL: dict[str, float] = {"nominatim": 1.1, "inarisk": 0.25}
_last_call: dict[str, float] = {}
#: One lock per provider, not one shared by all of them.
#:
#: A single lock meant a provider sleeping out its own interval blocked every
#: other provider from even checking theirs — Nominatim's 1.1 seconds held the
#: gate while nine InaRISK layers waited behind it for no reason. The intervals
#: exist to pace one provider, so they must not pace the others.
_throttle_locks: dict[str, asyncio.Lock] = {}


async def get_client() -> httpx.AsyncClient:
    """One connection pool per process, created on first use."""
    global _client
    if _client is None:
        async with _client_lock:
            if _client is None:
                settings = get_settings()
                _client = httpx.AsyncClient(
                    timeout=httpx.Timeout(settings.external_timeout_seconds),
                    follow_redirects=True,
                    # Deliberately permissive: Overpass answers 406 to a strict
                    # `Accept: application/json`. Providers that need something
                    # narrower pass their own header.
                    headers={
                        "Accept": "*/*",
                        "User-Agent": settings.nominatim_user_agent,
                    },
                    # A report fans out past ten calls on its own: InaRISK is
                    # nine or more hazard layers, NOAA/NCEI pages three times,
                    # and USGS, Overpass, Nominatim and the news feed are all in
                    # flight beside them. Capped at ten, the rest queued for a
                    # connection — and when a provider is down each waiter holds
                    # its slot for the full timeout before releasing it, so nine
                    # concurrent 8-second timeouts became a serial chain.
                    limits=httpx.Limits(max_connections=48, max_keepalive_connections=16),
                )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def _throttle(provider: str) -> None:
    interval = _MIN_INTERVAL.get(provider)
    if not interval:
        return
    lock = _throttle_locks.setdefault(provider, asyncio.Lock())
    async with lock:
        loop = asyncio.get_running_loop()
        elapsed = loop.time() - _last_call.get(provider, 0.0)
        if elapsed < interval:
            await asyncio.sleep(interval - elapsed)
        _last_call[provider] = loop.time()


async def _request(
    url: str,
    *,
    provider: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float | None = None,
    method: str = "GET",
    data: str | None = None,
) -> httpx.Response:
    """Perform one outbound call, mapping every failure onto a Tilik error."""
    client = await get_client()
    await _throttle(provider)

    try:
        response = await client.request(
            method,
            url,
            params=params,
            headers=headers,
            content=data,
            timeout=timeout,
        )
    except httpx.TimeoutException as exc:
        logger.warning("%s timed out: %s", provider, exc)
        raise UpstreamTimeoutError(detail=f"{provider} timed out") from exc
    except httpx.HTTPError as exc:
        logger.warning("%s request failed: %s", provider, exc)
        raise UpstreamUnavailableError(detail=f"{provider} is unreachable") from exc

    if response.status_code == 429:
        raise UpstreamRateLimitedError(detail=f"{provider} rate limited the request")
    if response.status_code >= 500:
        raise UpstreamUnavailableError(detail=f"{provider} returned {response.status_code}")
    if response.status_code >= 400:
        raise UpstreamUnavailableError(
            "A data provider rejected that request.",
            detail=f"{provider} returned {response.status_code}",
        )

    return response


#: Failures worth trying again, and the gap before doing so.
#:
#: A 504 from a shared public endpoint says the request queued too long, not
#: that the query is wrong — asking again a moment later usually works. Rate
#: limiting and unreachability are the same kind of "not now". A 4xx is not
#: retried: the request itself is wrong, and repeating it just burns the
#: provider's quota.
RETRIABLE_ERRORS = (UpstreamTimeoutError, UpstreamRateLimitedError, UpstreamUnavailableError)
RETRY_BACKOFF_SECONDS = 0.6


async def fetch_json(
    url: str,
    *,
    provider: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float | None = None,
    method: str = "GET",
    data: str | None = None,
    retries: int = 0,
) -> Any:
    """Call a provider and return decoded JSON.

    Raises a :class:`~api.core.errors.TilikError` subclass on any failure so
    callers can decide between "degrade gracefully" and "surface the error".

    `retries` is opt-in per caller rather than a default, because a retry is only
    safe where the call is a read. Overpass takes its query by POST and is still
    a read, while a POST elsewhere may not be — so the caller decides.
    """
    attempts = max(0, retries) + 1
    for attempt in range(attempts):
        try:
            response = await _request(
                url,
                provider=provider,
                params=params,
                headers=headers,
                timeout=timeout,
                method=method,
                data=data,
            )
            break
        except RETRIABLE_ERRORS as exc:
            if attempt + 1 >= attempts:
                raise
            logger.info(
                "%s failed (%s), retrying %d of %d",
                provider,
                exc.__class__.__name__,
                attempt + 1,
                attempts - 1,
            )
            await asyncio.sleep(RETRY_BACKOFF_SECONDS)

    try:
        return response.json()
    except ValueError as exc:
        raise UpstreamUnavailableError(detail=f"{provider} returned a non-JSON body") from exc


async def fetch_json_from_first(
    urls: list[str],
    *,
    provider: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float | None = None,
    method: str = "GET",
    data: str | None = None,
) -> tuple[Any, int]:
    """Try each host in turn, returning the first answer and its host's index.

    The index matters because an answer from a fallback is worth less than one
    from the primary: a mirror that only holds part of the planet returns an
    empty result rather than an error, and a caller has to be able to tell that
    apart from "the primary said there is nothing here".

    For endpoints that exist as a set of interchangeable mirrors. Overpass is the
    case in hand: its main host answers 504 when its shared queue is full and
    stops answering entirely once it has rate-limited an address, and the mirrors
    fail independently — measured together in one minute, the main host refused
    the connection, one mirror returned 502, two timed out, and one answered.

    One attempt per host rather than a retry each: the chain already is the
    retry, and multiplying the two turns a slow failure into a very slow one.
    Every host must be a mirror of the same data, since the caller cannot tell
    which one replied.
    """
    # The budget belongs to the chain, and what is left of it goes to the next
    # host.
    #
    # Two wrong versions came before this one. Giving each host the full timeout
    # meant a failing first host spent all of it and the second then started its
    # own: 32 seconds for a lookup budgeted at 16, which is how one dead mirror
    # pushed a whole report past the limit the frontend allows it. Splitting the
    # budget evenly fixed that and broke something else — a primary that refuses
    # a connection in one second forfeited its whole half, while the fallback got
    # 5 seconds for a request that needs 9, so it could never succeed at all.
    #
    # Measuring what is left means a fast failure hands its unspent time on, and
    # the worst case is still the timeout the caller asked for.
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout if timeout else None

    last: Exception | None = None
    for index, url in enumerate(urls):
        if deadline is not None:
            remaining = deadline - loop.time()
            # Below a second there is no point starting a request that has to
            # cross the internet; report the failure we already have.
            if remaining < 1.0 and last is not None:
                logger.info("%s chain out of budget after %d host(s)", provider, index)
                break
            per_host: float | None = max(remaining, 1.0)
        else:
            per_host = None
        try:
            payload = await fetch_json(
                url,
                provider=provider,
                params=params,
                headers=headers,
                timeout=per_host,
                method=method,
                data=data,
            )
            return payload, index
        except RETRIABLE_ERRORS as exc:
            last = exc
            if index + 1 < len(urls):
                logger.info(
                    "%s host %d of %d failed (%s), trying the next",
                    provider,
                    index + 1,
                    len(urls),
                    exc.__class__.__name__,
                )
    raise last if last else UpstreamUnavailableError(detail=f"{provider} has no hosts configured")


async def fetch_text(
    url: str,
    *,
    provider: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float | None = None,
) -> str:
    """Call a provider that answers with plain text (e.g. an ASCII DEM grid)."""
    response = await _request(
        url,
        provider=provider,
        params=params,
        headers=headers,
        timeout=timeout,
    )
    return response.text
