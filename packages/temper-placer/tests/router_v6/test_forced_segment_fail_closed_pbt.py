"""Property-based test for the forced-segment fail-closed gate (R1/R2).

Origin: docs/plans/2026-07-24-001-fix-forced-segment-fail-closed-plan.md,
Implementation Unit U3.

``_allow_forced_segments()`` was generalized from an HV/AC-only gate to an
unconditional close: whenever the plain A* pathfinder cannot find a legal,
clearance-respecting path for a net, it must be reported as failed rather
than drawing a zero-clearance forced segment -- regardless of net class.

This sweeps a representative range of net classes (including no
classification at all) against grids that are *guaranteed* unroutable
(a full-height wall, not Bernoulli obstacle density that may or may not
leave a path open -- see ``unroutable_wall_grids()``), and asserts the
invariant holds uniformly: never a forced segment, always an honest
failure report.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.router_v6._astar_reconstruct import run_astar_pathfinding
from temper_placer.router_v6.channel_mapping import ChannelMapping, ChannelPath
from temper_placer.router_v6.stage0_data import DesignRules
from tests.router_v6.astar_property_strategies import unroutable_wall_grids
from tests.router_v6.test_astar_route_multilayer_via_fallback import (
    _CONFIGURED_NET_CLASSES,
)
from tests.router_v6.test_astar_route_multilayer_via_fallback import (
    _configured_design_rules as _base_configured_design_rules,
)

# A net name that passes _should_route() for every configured class --
# none of GROUND_NET_PATTERNS/POWER_NET_PATTERNS/HV_NET_PATTERNS substring-
# match it, so classification never accidentally excludes it from A* before
# the gate is reached (the vacuousness this plan's own research diagnosed
# in the pre-existing HV/AC unit tests).
_NET_UNDER_TEST = "PROP_TEST_NET"

_SETTINGS = settings(max_examples=100, deadline=30000)


def _configured_design_rules(net_class: str | None) -> DesignRules:
    """Real per-class rules for _NET_UNDER_TEST, reusing the existing
    netclass-sizing-authority helper (test_astar_route_multilayer_via_fallback.py)
    rather than re-parsing configs/netclass_rules.yaml a second time. That
    helper's rules key off "NET_UNDER_TEST"; retarget to this file's net name.
    """
    base = _base_configured_design_rules(net_class)
    base.net_class_assignments = (
        {_NET_UNDER_TEST: net_class} if net_class is not None else {}
    )
    return base


def _assert_fails_closed(design_rules: DesignRules, grid_data, label: str) -> None:
    """Shared body for both properties below: run the unroutable case and
    assert the two invariants (no forced segment, honest failure report).
    """
    grid, start, goal = grid_data
    channel_path = ChannelPath(
        net_name=_NET_UNDER_TEST,
        channel_sequence=["ch_0"],
        waypoints=[start, goal],
        total_length=abs(goal[0] - start[0]) + abs(goal[1] - start[1]),
        preferred_layer="F.Cu",
    )

    result = run_astar_pathfinding(
        ChannelMapping({_NET_UNDER_TEST: channel_path}),
        grid,
        design_rules=design_rules,
        max_iter=10_000,
    )

    # Never a forced segment, regardless of class.
    routed = result.routed_paths.get(_NET_UNDER_TEST)
    assert routed is None or routed.forced_segment_count == 0, (
        f"{label}: a forced segment survived "
        f"(forced_segment_count={getattr(routed, 'forced_segment_count', None)})"
    )
    # Always an honest failure report -- not silently dropped.
    assert _NET_UNDER_TEST in result.failed_nets, (
        f"{label}: unroutable net must be reported failed, "
        f"not silently absent (failed_nets={result.failed_nets})"
    )


@pytest.mark.property
@given(
    net_class=st.sampled_from(_CONFIGURED_NET_CLASSES + (None,)),
    grid_data=unroutable_wall_grids(),
)
@_SETTINGS
def test_no_forced_segment_survives_for_any_net_class(net_class, grid_data):
    """R1/R2: for any net class (or none), an unroutable net fails honestly."""
    _assert_fails_closed(
        _configured_design_rules(net_class), grid_data, f"net_class={net_class!r}"
    )


@pytest.mark.property
@given(grid_data=unroutable_wall_grids())
@_SETTINGS
def test_unclassified_net_also_fails_closed(grid_data):
    """R2 edge case: a net with no netclass assignment at all -- not even a
    "Default" entry in design_rules.net_classes -- must still fail closed,
    not silently allowed through a missing-classification loophole. Distinct
    from the net_class=None case above (which still sweeps real configured
    classes for *other* nets; this one has no classes registered at all).
    """
    _assert_fails_closed(DesignRules(), grid_data, "unclassified net, empty DesignRules")
