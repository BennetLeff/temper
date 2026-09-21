"""Test-local fixtures for the store suite."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from temper_harness.store import header_allowlist


@pytest.fixture(autouse=True)
def _fresh_allowlist_cache() -> Iterator[None]:
    """Keep the allowlist's memo from leaking between tests.

    ``header_allowlist`` is ``lru_cache``d because it reads a committed file, and
    the tests that mutate what it reads must not leave the mutated value behind
    for the next test. Clearing on both sides means a fault-injection test cannot
    pass by inheriting a real answer, nor fail by leaving a fake one.
    """
    header_allowlist.cache_clear()
    yield
    header_allowlist.cache_clear()
