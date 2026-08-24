"""A tiny in-process TTL cache.

Serverless instances are short-lived, so this mostly helps during a burst of
requests on one warm instance — enough to keep us inside Nominatim's usage
policy without adding Redis to a base project.
"""

from __future__ import annotations

import time
from typing import Any


class TTLCache:
    def __init__(self, *, ttl_seconds: int, max_entries: int = 256) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at < time.monotonic():
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        if len(self._store) >= self._max_entries:
            # Cheap eviction: drop whatever expires soonest.
            oldest = min(self._store, key=lambda k: self._store[k][0])
            self._store.pop(oldest, None)
        self._store[key] = (time.monotonic() + self._ttl, value)

    def clear(self) -> None:
        self._store.clear()
