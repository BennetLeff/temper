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
    config.addinivalue_line(
        "markers",
        "nightly: tests that run only in scheduled nightly CI "
        "(too heavy for per-commit; opt-in with -m nightly)",
    )
    config.addinivalue_line(
        "markers",
        "bmc_l0_encoding: BMC L0 encoding correctness tests (pre-solve verification)",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Skip nightly-marked tests unless explicitly selected or running in
    a nightly CI context (RUN_NIGHTLY env var or -m nightly flag)."""
    import os

    run_nightly = (
        config.getoption("-m", default="") == "nightly"
        or "nightly" in (config.getoption("-m", default="") or "")
        or os.environ.get("RUN_NIGHTLY") == "1"
    )
    if not run_nightly:
        skip_nightly = pytest.mark.skip(reason="nightly test — use -m nightly or RUN_NIGHTLY=1")
        for item in items:
            if "nightly" in item.keywords:
                item.add_marker(skip_nightly)


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
