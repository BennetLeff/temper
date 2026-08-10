"""Shared fixtures and Hypothesis profiles for router_v6 test suite.

# @req(N10, U1): CI budget benchmarks — Hypothesis profiles + low-priority marker

Provides CI-fast and CI-full Hypothesis profiles so individual test
files can opt into tiered PBT execution without hard-coding
max_examples values.
"""

from __future__ import annotations

import sys

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


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
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


# The 8 Stage-2 validator modules and the registry names their top-level
# `@register_validator` decorators produce. Mirrors the lists in
# `test_inductive_ladder.py`; kept here because the autouse fixture needs the
# same mapping to re-establish the baseline registration.
_VALIDATOR_NAME_TO_MODULE: dict[str, str] = {
    "ObstacleMap": "temper_placer.router_v6.obstacle_map",
    "RoutingSpace": "temper_placer.router_v6.routing_space",
    "ChannelSkeleton": "temper_placer.router_v6.channel_skeleton",
    "ChannelWidths": "temper_placer.router_v6.channel_widths",
    "OccupancyGrid": "temper_placer.router_v6.occupancy_grid",
    "LayerCapacity": "temper_placer.router_v6.layer_capacity",
    "RoutingDemand": "temper_placer.router_v6.routing_demand",
    "BottleneckAnalysis": "temper_placer.router_v6.bottleneck_analysis",
}


def _re_execute_validator_module(name: str, module_name: str) -> None:
    """Re-execute one validator module's body into a FRESH module object.

    The body's top-level ``@register_validator`` decorators re-run against the
    shared ``VALIDATOR_REGISTRY`` (idempotent — ``register_validator`` dedupes
    by function identity). The fresh module is registered in ``sys.modules``
    only for the duration of the exec (dataclass machinery looks up
    ``sys.modules[cls.__module__]``) and then the ORIGINAL module object is
    restored, so every existing reference keeps its identity -- critically,
    exception classes (e.g. ``routing_space.RoutingSpaceEmptyError``) remain
    the same objects, unlike ``importlib.reload``.
    """
    import importlib
    import importlib.util

    mod = importlib.import_module(module_name)
    spec = importlib.util.spec_from_file_location(module_name, mod.__file__)
    fresh = importlib.util.module_from_spec(spec)
    saved = sys.modules[module_name]
    sys.modules[module_name] = fresh
    try:
        spec.loader.exec_module(fresh)
    finally:
        sys.modules[module_name] = saved


def _ensure_baseline_validators_registered() -> None:
    """Repopulate the registry for any Stage-2 validator that is missing.

    Fixes #919: tests that call ``clear_validators()``
    (``test_stage_validators``, ``test_coverage_paydown_wave3_f``) empty the
    module-global ``VALIDATOR_REGISTRY``; because the validator modules are
    already in ``sys.modules``, later ``import`` statements do not re-execute
    their decorators. Re-executing the missing modules' bodies (fresh objects,
    identity-preserving) re-establishes the baseline regardless of ordering.
    """
    from temper_placer.router_v6.stage_validators import VALIDATOR_REGISTRY

    registered = set(VALIDATOR_REGISTRY)
    for name, module_name in _VALIDATOR_NAME_TO_MODULE.items():
        if name not in registered:
            _re_execute_validator_module(name, module_name)


@pytest.fixture(autouse=True)
def _isolate_validator_registry():
    """Snapshot/restore the router_v6 validator registry around every test.

    Every registry mutation (add/clear) is made test-local, and the baseline
    Stage-2 validator registration is re-established when a test leaves it
    incomplete. See ``_ensure_baseline_validators_registered`` for the #919
    rationale.
    """
    from temper_placer.router_v6.stage_validators import VALIDATOR_REGISTRY

    snapshot = {k: list(v) for k, v in VALIDATOR_REGISTRY.items()}
    yield
    VALIDATOR_REGISTRY.clear()
    VALIDATOR_REGISTRY.update(snapshot)
    _ensure_baseline_validators_registered()


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
