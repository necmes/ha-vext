"""Pure backoff policy for the Vext coordinator.

Kept free of Home Assistant imports so it can be unit-tested standalone.
"""
from __future__ import annotations

from datetime import timedelta


class BackoffPolicy:
    """Exponential backoff between the base interval and a hard ceiling."""

    def __init__(
        self,
        base: timedelta,
        maximum: timedelta,
        factor: float = 2.0,
    ) -> None:
        if base <= timedelta(0):
            raise ValueError("base interval must be positive")
        if maximum < base:
            maximum = base
        if factor < 1.0:
            raise ValueError("factor must be >= 1.0")
        self._base = base
        self._max = maximum
        self._factor = factor
        self._failures = 0

    @property
    def failures(self) -> int:
        return self._failures

    def reset(self) -> timedelta:
        """Call after a successful update. Returns the base interval."""
        self._failures = 0
        return self._base

    def failure(self, retry_after: float | None = None) -> timedelta:
        """Call after a failed update. Returns the next interval to use.

        `retry_after` (seconds, from an HTTP 429/503 hint) wins when it asks
        for a longer wait than the computed backoff.
        """
        self._failures += 1
        seconds = self._base.total_seconds() * (self._factor ** (self._failures - 1))
        if retry_after is not None and retry_after > seconds:
            seconds = retry_after
        return min(timedelta(seconds=seconds), self._max)
