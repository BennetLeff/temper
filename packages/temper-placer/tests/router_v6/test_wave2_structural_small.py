"""
Wave 2 PR — Structural Small Fixes

Verifies the three structural small requirements from the
closure-rate rollout plan.

R4: Layer switching at SMD pads is enabled (the ``tht_locations``
    gate no longer blocks multilayer routing when an alternate grid
    is available).
R5: ``base_inflation`` is reduced to ``trace_width / 2`` only at
    both call sites (pad-unblock and C-Space grid build). The
    clearance term was double-counted (once by the router, once
    by KiCad DRC).
R6: Direct-attempt A* fallback creates a ``ChannelPath`` with
    pad-to-pad waypoints for any net without a SAT channel
    assignment. Already implemented in ``_run_stage4``.
"""
from __future__ import annotations

import inspect

import pytest

from temper_placer.router_v6.occupancy_grid import OccupancyGridStage


def test_r4_layer_switching_no_longer_requires_tht():
    """``_astar_route_with_ripup`` allows multilayer routing when
    ``alternate_grid`` is present, regardless of THT pads.

    The previous gate at line 367 was ``if alternate_grid and
    tht_locations:``; the new gate is ``if alternate_grid:``.  When
    THT pads are present they remain the preferred layer-switch
    site (handled inside ``_astar_route_multilayer``).
    """
    from temper_placer.router_v6.astar_pathfinding import (
        _astar_route_with_ripup,
    )

    source = inspect.getsource(_astar_route_with_ripup)
    # The gate should mention alternate_grid at the boundary check
    assert "if alternate_grid:" in source, (
        "Layer-switching gate in _astar_route_with_ripup should be "
        "'if alternate_grid:' (no longer requires tht_locations)."
    )
    # The old combined form should be gone
    assert "if alternate_grid and tht_locations:" not in source, (
        "Old gate 'if alternate_grid and tht_locations:' should be "
        "removed; layer switching is now allowed at SMD pads too."
    )


def test_r5_base_inflation_drops_clearance_at_pad_unblock():
    """``base_inflation`` in ``_astar_route_with_ripup`` is now
    ``trace_width / 2`` only (no clearance term). The clearance was
    double-counted (router + KiCad DRC).
    """
    from temper_placer.router_v6.astar_pathfinding import (
        _astar_route_with_ripup,
    )

    source = inspect.getsource(_astar_route_with_ripup)
    # The base_inflation definition should not add the clearance term
    assert "default_clearance_mm" not in source, (
        "base_inflation in _astar_route_with_ripup should not include "
        "default_clearance_mm; only trace_width/2. R5 dropped the "
        "double-counted clearance term."
    )


def test_r5_base_inflation_drops_clearance_at_occupancy_grid():
    """``base_inflation`` in ``OccupancyGridStage.run`` is also
    reduced to ``trace_width / 2`` only.
    """
    source = inspect.getsource(OccupancyGridStage.run)
    assert "default_clearance_mm" not in source, (
        "base_inflation in OccupancyGridStage.run should not include "
        "default_clearance_mm; only trace_width/2."
    )


def test_r6_stage4_has_sat_skipped_fallback():
    """``_run_stage4`` creates a fallback ``ChannelPath`` for any net
    without a SAT channel assignment.

    The fallback is the pad-to-pad direct path with
    ``preferred_layer="F.Cu"``. This makes SAT-skipped nets visible
    in the closure test's ``completion_rate`` instead of silently
    dropping them.
    """
    from temper_placer.router_v6.pipeline import RouterV6Pipeline

    source = inspect.getsource(RouterV6Pipeline._run_stage4)
    assert "Fallback" in source, (
        "_run_stage4 must contain a fallback path for nets without "
        "a SAT channel assignment. R6 depends on this."
    )
    assert "channel_sequence=[]" in source or "channel_sequence=()" in source, (
        "Fallback ChannelPath must have an empty channel_sequence "
        "(direct pad-to-pad waypoints, no skeleton path)."
    )
    assert "preferred_layer=\"F.Cu\"" in source, (
        "Fallback ChannelPath must use F.Cu as the preferred layer."
    )
