"""Error types and the handlers that turn them into clean JSON.

Nothing raised inside a service should ever reach the user as a traceback: the
handlers below own the entire non-2xx surface of the API.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("tilik.api")


class TilikError(Exception):
    """Base class for failures that carry a user-safe message."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "internal_error"
    message: str = "Something went wrong on our side."

    def __init__(self, message: str | None = None, *, detail: str | None = None) -> None:
        self.message = message or self.message
        self.detail = detail
        super().__init__(self.message)


class InvalidCoordinatesError(TilikError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "invalid_coordinates"
    message = "Those coordinates aren't on Earth. Latitude must be -90..90 and longitude -180..180."


class InvalidQueryError(TilikError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "invalid_query"
    message = "That search query can't be used."


class LocationNotFoundError(TilikError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "location_not_found"
    message = "We couldn't find a place matching that."


class UpstreamTimeoutError(TilikError):
    status_code = status.HTTP_504_GATEWAY_TIMEOUT
    code = "upstream_timeout"
    message = "A data provider took too long to answer. Try again in a moment."


class UpstreamUnavailableError(TilikError):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = "upstream_unavailable"
    message = "A data provider is unavailable right now."


class UpstreamRateLimitedError(TilikError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "upstream_rate_limited"
    message = "We're being rate limited by a data provider. Give it a few seconds."


class RateLimitedError(TilikError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"
    message = "Too many requests. Slow down a little."


class DatabaseUnavailableError(TilikError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "database_unavailable"
    message = "Our spatial database is unreachable right now."


def _error_body(code: str, message: str, detail: str | None = None) -> dict[str, object]:
    return {"error": {"code": code, "message": message, "detail": detail}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(TilikError)
    async def _handle_tilik_error(_: Request, exc: TilikError) -> JSONResponse:
        headers = {"Retry-After": "10"} if exc.status_code == 429 else None
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.code, exc.message, exc.detail),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else None
        field = ".".join(str(part) for part in (first or {}).get("loc", [])[1:]) or "request"
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_body(
                "invalid_parameters",
                f"Check the `{field}` parameter.",
                str((first or {}).get("msg", "")) or None,
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        code = "not_found" if exc.status_code == 404 else "http_error"
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(code, message),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Log the real thing, hand the user something safe.
        logger.exception("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body("internal_error", TilikError.message),
        )
