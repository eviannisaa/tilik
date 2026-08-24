"""Shared handling for Overpass responses.

Overpass reports some failures inside a successful response. A query that runs
out of time comes back as HTTP 200 with an empty `elements` array and a
`remark` naming the error:

    {"elements": [], "remark": "runtime error: Query timed out in \\"query\\" ..."}

Read as JSON and trusted, that is indistinguishable from a healthy answer for a
place where nothing is mapped — so a failed lookup became the claim that a plot
has no clinic, no school and no shop within 1.5 km. Every other provider failure
in this codebase surfaces as `unavailable`, and this one has to as well.
"""

from __future__ import annotations

import logging
from typing import Any

from api.core.errors import UpstreamUnavailableError

logger = logging.getLogger(__name__)


def elements_of(
    payload: Any, *, provider: str, trust_empty: bool = True
) -> list[dict]:
    """The `elements` of an Overpass response, or a failure if it carries one.

    Raises :class:`UpstreamUnavailableError` on a `remark`, so callers handle it
    on the same path they already handle a timeout or a 504.

    `trust_empty` says whether an empty result may be reported as a finding.
    Pass `False` for an answer from a fallback host: a mirror that holds only
    part of the planet answers 200 with nothing rather than failing.
    `overpass.osm.ch` is the case that proved it — 30 banks in Zurich, zero in
    Indonesia, because its database is Switzerland only. As a fallback it was
    worse than a dead host: it succeeded, so the section was never marked
    unavailable, and a plot in Serpong with 120 mapped places was reported as
    having none.
    """
    if not isinstance(payload, dict):
        return []

    remark = payload.get("remark")
    if isinstance(remark, str) and remark.strip():
        # Overpass also uses `remark` for harmless notices, but every one of
        # those still returns the data it found; an error remark comes with
        # nothing. Treating "remark and no elements" as the failure keeps a
        # partial answer usable.
        elements = payload.get("elements") or []
        if not elements:
            logger.warning("%s reported: %s", provider, remark.strip())
            raise UpstreamUnavailableError(
                detail=f"{provider} reported: {remark.strip()[:120]}"
            )

    elements = [
        element for element in payload.get("elements", []) if isinstance(element, dict)
    ]

    if not elements and not trust_empty:
        logger.warning("%s fallback host returned nothing; not treating as empty", provider)
        raise UpstreamUnavailableError(
            detail=f"{provider} fallback host returned no data for this area"
        )

    return elements
