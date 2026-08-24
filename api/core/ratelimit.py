"""A small per-IP request cap.

This is a courtesy limit that protects the upstream providers from one runaway
client. It is per-process, so on serverless it bounds a single warm instance
rather than the whole deployment — put a real limiter at the edge if you need
hard guarantees.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

WINDOW_SECONDS = 60.0
#: Health checks shouldn't be able to exhaust a client's budget.
EXEMPT_PATHS = frozenset({"/api/health", "/api/docs", "/api/openapi.json"})


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, requests_per_minute: int) -> None:
        super().__init__(app)
        self._limit = requests_per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _client_key(self, request: Request) -> str:
        # Vercel and most proxies put the real client first in X-Forwarded-For.
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if self._limit <= 0 or request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        key = self._client_key(request)
        now = time.monotonic()
        hits = self._hits[key]

        while hits and now - hits[0] > WINDOW_SECONDS:
            hits.popleft()

        if len(hits) >= self._limit:
            retry_after = max(1, int(WINDOW_SECONDS - (now - hits[0])))
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(retry_after)},
                content={
                    "error": {
                        "code": "rate_limited",
                        "message": "Too many requests. Slow down a little.",
                        "detail": f"Limit is {self._limit} requests per minute.",
                    }
                },
            )

        hits.append(now)

        # Stop idle clients accumulating in memory on a long-lived instance.
        if len(self._hits) > 2048:
            stale = [
                key
                for key, seen in self._hits.items()
                if not seen or now - seen[-1] > WINDOW_SECONDS
            ]
            for stale_key in stale:
                self._hits.pop(stale_key, None)

        return await call_next(request)
