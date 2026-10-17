"""Sliding-window rate limiter keyed by client IP (in-memory, per process)."""

import hashlib
import time
from collections import deque
from collections.abc import Callable

from fastapi import Request


class RateLimiter:
    """Allow `limit` hits per `window` seconds per key."""

    def __init__(
        self, limit: int, window: float = 3600.0, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.limit, self.window, self._clock = limit, window, clock
        self._hits: dict[str, deque[float]] = {}

    def check(self, key: str) -> tuple[bool, int]:
        """Record a hit. Returns (allowed, retry_after_seconds)."""
        now = self._clock()
        q = self._hits.setdefault(key, deque())
        while q and now - q[0] >= self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False, max(1, int(self.window - (now - q[0])) + 1)
        q.append(now)
        if len(self._hits) > 10_000:  # bound memory
            self._hits = {k: v for k, v in self._hits.items() if v and now - v[-1] < self.window}
        return True, 0


def client_ip(request: Request, trusted_hops: int = 1) -> str:
    """Client IP behind `trusted_hops` proxies: take the entry the nearest proxy appended.

    The left-most X-Forwarded-For entries are client-controlled and spoofable, so we count
    from the right.
    """
    xff = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    if xff and trusted_hops > 0:
        return xff[-trusted_hops] if len(xff) >= trusted_hops else xff[0]
    return request.client.host if request.client else "unknown"


def hash_ip(ip: str) -> str:
    """Short one-way hash so raw IPs are never stored."""
    return hashlib.sha256(ip.encode()).hexdigest()[:16]
