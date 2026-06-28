"""
Smoke test for the coupled diff pair router import.

Background
----------
The coupled diff pair router (``CoupledDiffPairRouter`` in
``temper_placer.routing.coupled_diff_pair_router``) handles routing for
all differential pairs. This test verifies the import resolves cleanly
through normal package machinery (no ``sys.path`` hack).
"""

import pytest

from temper_placer.routing.coupled_diff_pair_router import (
    CoupledDiffPairRouter,
    CoupledRouterResult,
)


def test_coupled_router_imports_successfully() -> None:
    """The coupled diff pair router module is present and importable.

    Asserts the module imports directly from the routing package without
    any sys.path manipulation, using standard package machinery.
    """
    router = CoupledDiffPairRouter()
    assert router is not None
    assert isinstance(router, CoupledDiffPairRouter)


def test_coupled_router_result_importable() -> None:
    """CoupledRouterResult is importable and constructible."""
    result = CoupledRouterResult(
        success=True,
        pos_path=[(0.0, 0.0, 0), (1.0, 0.0, 0)],
        neg_path=[(0.0, 0.25, 0), (1.0, 0.25, 0)],
        coupling_ratio=100.0,
        max_skew_mm=0.0,
        avg_separation_mm=0.25,
        routing_time_s=0.001,
    )
    assert result.success
    assert result.error_message is None
