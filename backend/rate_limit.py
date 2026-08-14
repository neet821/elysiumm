"""Thread-safe in-process sliding-window rate limiting primitives."""

from __future__ import annotations

from collections import defaultdict, deque
import math
from threading import Lock
import time
from typing import Callable


class SlidingWindowRateLimiter:
    def __init__(self, clock: Callable[[], float] | None = None):
        self._clock = clock or time.monotonic
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    @staticmethod
    def _validate(limit: int, window_seconds: int | float) -> None:
        if limit < 1 or window_seconds <= 0:
            raise ValueError("rate limit and window must be positive")

    @staticmethod
    def _prune(events: deque[float], now: float, window_seconds: float) -> None:
        cutoff = now - window_seconds
        while events and events[0] <= cutoff:
            events.popleft()

    def retry_after(self, key: str, *, limit: int, window_seconds: float) -> int:
        self._validate(limit, window_seconds)
        now = self._clock()
        with self._lock:
            events = self._events.get(key)
            if not events:
                return 0
            self._prune(events, now, window_seconds)
            if not events:
                self._events.pop(key, None)
                return 0
            if len(events) < limit:
                return 0
            return max(1, math.ceil(window_seconds - (now - events[0])))

    def check(self, key: str, *, limit: int, window_seconds: float) -> int:
        """Record an attempt, returning retry seconds when it must be denied."""
        self._validate(limit, window_seconds)
        now = self._clock()
        with self._lock:
            events = self._events[key]
            self._prune(events, now, window_seconds)
            if len(events) >= limit:
                return max(1, math.ceil(window_seconds - (now - events[0])))
            events.append(now)
            return 0

    def clear(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._events.clear()
            else:
                self._events.pop(key, None)
