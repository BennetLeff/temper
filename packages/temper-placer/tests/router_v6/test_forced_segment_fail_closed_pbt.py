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

from pathlib import Path

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.router_v6._astar_reconstruct import run_astar_pathfinding
from temper_placer.router_v6.channel_mapping import ChannelMapping, ChannelPath
from temper_placer.router_v6.stage0_data import DesignRules, NetClassRules
from tests.router_v6.astar_property_strategies import unroutable_wall_grids

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[4]
_NETCLASS_CONFIG = yaml.safe_load(
    (_REPO_ROOT / "packages/temper-placer/configs/netclass_rules.yaml").read_text()
)
_CONFIGURED_NET_CLASSES = tuple(_NETCLASS_CONFIG["classes"])

# A net name that passes _should_route() for every configured class --
# none of GROUND_NET_PATTERNS/POWER_NET_PATTERNS/HV_NET_PATTERNS substring-
# match it, so classification never accidentally excludes it from A* before
# the gate is reached (the vacuousness this plan's own research diagnosed
# in the pre-existing HV/AC unit tests).
_NET_UNDER_TEST = "PROP_TEST_NET"

_SETTINGS = settings(max_examples=100, deadline=30000)


def _configured_design_rules(net_class: str | None) -> DesignRules:
    """Construct real per-class rules from the netclass sizing authority."""
    net_classes = {
        name: NetClassRules(
            name=name,
            clearance_mm=spec["clearance"],
            trace_width_mm=spec["trace_width"],
            via_diameter_mm=spec["via_diameter"],
            via_drill_mm=spec["via_drill"],
            safety_category=spec.get("safety_category"),
        )
        for name, spec in _NETCLASS_CONFIG["classes"].items()
    }
    assignments = (
        {_NET_UNDER_TEST: net_class} if net_class is not None else {}
    )
    return DesignRules(
        net_classes=net_classes,
        net_class_assignments=assignments,
        default_clearance_mm=_NETCLASS_CONFIG["default_clearance_mm"],
        default_trace_width_mm=0.2,
        default_via_diameter_mm=0.6,
        default_via_drill_mm=0.3,
    )


@pytest.mark.property
@given(
    net_class=st.sampled_from(_CONFIGURED_NET_CLASSES + (None,)),
    grid_data=unroutable_wall_grids(),
)
@_SETTINGS
def test_no_forced_segment_survives_for_any_net_class(net_class, grid_data):
    """R1/R2: for any net class (or none), an unroutable net fails honestly."""
    grid, start, goal = grid_data
    design_rules = _configured_design_rules(net_class)

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
        f"net_class={net_class!r}: a forced segment survived "
        f"(forced_segment_count={getattr(routed, 'forced_segment_count', None)})"
    )
    # Always an honest failure report -- not silently dropped.
    assert _NET_UNDER_TEST in result.failed_nets, (
        f"net_class={net_class!r}: unroutable net must be reported failed, "
        f"not silently absent (failed_nets={result.failed_nets})"
    )


@pytest.mark.property
@given(grid_data=unroutable_wall_grids())
@_SETTINGS
def test_unclassified_net_also_fails_closed(grid_data):
    """R2 edge case: a net with no netclass assignment at all -- falling
    through to the "Default" class -- must still fail closed, not silently
    allowed through a missing-classification loophole.
    """
    grid, start, goal = grid_data
    design_rules = DesignRules()  # no net_classes, no assignments at all

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

    routed = result.routed_paths.get(_NET_UNDER_TEST)
    assert routed is None or routed.forced_segment_count == 0
    assert _NET_UNDER_TEST in result.failed_nets
