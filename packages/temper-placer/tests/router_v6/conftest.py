"""Shared fixtures and Hypothesis profiles for router_v6 test suite.

# @req(N10, U1): CI budget benchmarks — Hypothesis profiles + low-priority marker

Provides CI-fast and CI-full Hypothesis profiles so individual test
files can opt into tiered PBT execution without hard-coding
max_examples values.
"""

from __future__ import annotations

import pytest
from hypothesis import settings


def pytest_configure(config: pytest.Config) -> None:
    """Register Hypothesis profiles and custom markers."""
    _register_profiles()
    config.addinivalue_line(
        "markers",
        "pbt_low_priority: PBT tests that can be skipped under CI-fast to meet time budget",
    )


def _register_profiles() -> None:
    """Register CI-fast and CI-full Hypothesis profiles."""
    settings.register_profile(
        "CI-fast",
        max_examples=50,
        deadline=5000,
        print_blob=False,
        suppress_health_check=[],
    )
    settings.register_profile(
        "CI-full",
        max_examples=200,
        deadline=15000,
        print_blob=False,
        suppress_health_check=[],
    )
    # Default: use CI-fast in CI, CI-full locally
    import os

    default_profile = "CI-full" if os.environ.get("CI") else "CI-fast"
    settings.load_profile(default_profile)
