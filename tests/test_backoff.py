"""Unit tests for the pure backoff policy."""
from __future__ import annotations

from datetime import timedelta

import pytest

from custom_components.vext.backoff import BackoffPolicy

BASE = timedelta(seconds=120)
MAX = timedelta(minutes=30)


def test_rejects_non_positive_base() -> None:
    with pytest.raises(ValueError):
        BackoffPolicy(timedelta(0), MAX)


def test_rejects_factor_below_one() -> None:
    with pytest.raises(ValueError):
        BackoffPolicy(BASE, MAX, factor=0.9)


def test_maximum_never_below_base() -> None:
    policy = BackoffPolicy(BASE, timedelta(seconds=1))
    assert policy.failure() == BASE


def test_doubles_on_each_failure_then_caps() -> None:
    policy = BackoffPolicy(BASE, MAX)
    assert policy.failure() == timedelta(seconds=120)
    assert policy.failure() == timedelta(seconds=240)
    assert policy.failure() == timedelta(seconds=480)
    assert policy.failure() == timedelta(seconds=960)
    assert policy.failure() == MAX  # 1920s would exceed the ceiling
    assert policy.failure() == MAX
    assert policy.failures == 6


def test_reset_returns_base_and_clears_failures() -> None:
    policy = BackoffPolicy(BASE, MAX)
    policy.failure()
    policy.failure()
    assert policy.reset() == BASE
    assert policy.failures == 0
    assert policy.failure() == BASE


def test_retry_after_wins_when_longer() -> None:
    policy = BackoffPolicy(BASE, MAX)
    assert policy.failure(retry_after=600) == timedelta(seconds=600)


def test_retry_after_ignored_when_shorter_than_backoff() -> None:
    policy = BackoffPolicy(BASE, MAX)
    policy.failure()
    policy.failure()  # next computed backoff is 480s
    assert policy.failure(retry_after=10) == timedelta(seconds=480)


def test_retry_after_still_capped_by_maximum() -> None:
    policy = BackoffPolicy(BASE, MAX)
    assert policy.failure(retry_after=99999) == MAX


def test_custom_factor() -> None:
    policy = BackoffPolicy(BASE, MAX, factor=1.0)
    assert policy.failure() == BASE
    assert policy.failure() == BASE
