# @req(APC1, R3): all-pad routing connectivity — truthful completion reporting
# @req(APC1, R4): completion derived from connectivity, not path count

"""RED (TDD): Truthful completion reporting — U3 of plan APC1.

PathfindingResult and RoutingResults must derive completion from connectivity
verification, not from the count of route-path objects.  A net with 3 required
pads that only routes 2 pads must be INCOMPLETE, never counted as success.

These tests FAIL until U3 implementation lands.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from temper_placer.router_v6.astar_core import RoutePath
from temper_placer.router_v6.connectivity import (
    CopperPad,
    CopperTrack,
    NetConnectivity,
    NetDisposition,
    PadIdentity,
    Point,
)
from temper_placer.router_v6.routing_results import (
    RoutingResults,
    compile_routing_results,
)

# =========================================================================
# Helpers
# =========================================================================


def _pid(ref: str, pad: str, net: str, x: float = 0.0, y: float = 0.0) -> PadIdentity:
    return PadIdentity(component_ref=ref, pad=pad, net=net, x=x, y=y, layers=(0,))


def _point(x: float = 0.0, y: float = 0.0) -> Point:
    return Point(x=x, y=y)


def _pad(ref: str, pad: str, net: str, x: float = 0.0, y: float = 0.0) -> CopperPad:
    return CopperPad(
        identity=_pid(ref, pad, net, x, y),
        center=_point(x, y),
        shape="rect",
        size=(1.0, 1.0),
    )


def _track(
    net: str, x1: float, y1: float, x2: float, y2: float, layer: str = "F.Cu"
) -> CopperTrack:
    return CopperTrack(
        net=net,
        start=_point(x1, y1),
        end=_point(x2, y2),
        width_mm=0.2,
        layer=layer,
    )


PRODUCTION_RESULT = (
    '{"unconnected_count":149,"violations":[{"type":"unconnected_items"}]}'
)
"""Fake KiCad JSON — documents contracts without requiring a KiCad install."""


# =========================================================================
# TDD tests — RED until U3 lands
# =========================================================================


class TestRoutingResultsDerivesCompletionFromConnectivity:
    """RED: RoutingResults.success_count must reflect NetDisposition."""

    def test_success_count_is_zero_when_all_nets_are_incomplete(self):
        """Three-pad net routed via a two-pad path → INCOMPLETE, not success."""
        connectivity = {
            "NET": NetConnectivity(
                net="NET",
                disposition=NetDisposition.INCOMPLETE,
                connected_pad_count=2,
                total_required_pad_count=3,
                components=(),
                unresolved_islands=((),),
            ),
        }
        # A RoutingResults that only has paths but carries connectivity
        # must NOT count incomplete nets as successful.
        rr = RoutingResults(compiled_routes={}, failed_nets=[], connectivity=connectivity)
        # With connectivity, success must come from dispositions, not path count.
        assert rr.success_count == 0, (
            "Net is INCOMPLETE — must not contribute to success_count"
        )

    def test_zero_required_pads_yields_exempt_not_incomplete(self):
        """A net with no required pads gets EXEMPT, not counted as failure."""
        connectivity = {
            "net_only_pads": NetConnectivity(
                net="net_only_pads",
                disposition=NetDisposition.EXEMPT,
                connected_pad_count=0,
                total_required_pad_count=0,
                components=(),
                unresolved_islands=(),
            ),
        }
        rr = RoutingResults(compiled_routes={}, failed_nets=[], connectivity=connectivity)
        assert rr.success_count == 0  # exempt ≠ success
        assert rr.failure_count == 0  # exempt ≠ failure either

    def test_backward_compatible_when_connectivity_is_none(self):
        """When connectivity is None (pre-U3), fall back to path-count logic."""
        rr = RoutingResults(compiled_routes={"NET": None, "NET2": None}, failed_nets=[])  # type: ignore
        # With connectivity=None, success_count must use path-count fallback.
        # Two paths = 2 successes in this case (the old behaviour).
        assert rr.success_count == 2, f"expected 2, got {rr.success_count}"
        assert rr.failure_count == 0

    def test_plane_connected_counts_as_success(self):
        """An explicit plane_connected disposition counts as success."""
        connectivity = {
            "GND": NetConnectivity(
                net="GND",
                disposition=NetDisposition.PLANE_CONNECTED,
                connected_pad_count=5,
                total_required_pad_count=5,
                components=(),
                unresolved_islands=(),
            ),
        }
        rr = RoutingResults(compiled_routes={}, failed_nets=[], connectivity=connectivity)
        assert rr.success_count == 1


class TestCompiledRouteCarriesOnlyRoutedDisposition:
    """RED: compile_routing_results must exclude incomplete tree routes."""

    def test_compile_excludes_incomplete_dispositions(self):
        """An INCOMPLETE tree must not become a CompiledRoute."""

        from temper_placer.router_v6.terminal_tree import TerminalTreeEdge
        from temper_placer.router_v6.tree_route_geometry import (
            TreeRouteBranch,
            TreeRouteGeometry,
        )

        edge = TerminalTreeEdge(
            _pid("U1", "1", "NET1"), _pid("U1", "2", "NET1")
        )
        branch = TreeRouteBranch(
            edge=edge,
            path=RoutePath(
                net_name="NET1",
                coordinates=[(0.0, 0.0), (1.0, 1.0)],
                layer_name="F.Cu",
                path_length=1.4,
                forced_segment_count=0,
            ),
        )
        geometry = TreeRouteGeometry(net_name="NET1", branches=(branch,))

        connectivity = {
            "NET1": NetConnectivity(
                net="NET1",
                disposition=NetDisposition.INCOMPLETE,
                connected_pad_count=1,
                total_required_pad_count=2,
                components=(),
                unresolved_islands=(),
            ),
        }

        from temper_placer.router_v6.astar_pathfinding import PathfindingResult
        from temper_placer.router_v6.trace_width_assignment import TraceWidthAssignment
        from temper_placer.router_v6.via_placement import ViaPlacement

        compiled = compile_routing_results(
            PathfindingResult(
                routed_paths={},
                tree_routes={"NET1": geometry},
                failed_nets=[],
            ),
            width_assignment=TraceWidthAssignment(assignments={}),
            via_placement=ViaPlacement(vias=[]),
            connectivity=connectivity,
        )
        # NET1 is INCOMPLETE — it must NOT appear in tree_routes.
        assert "NET1" not in compiled.tree_routes
        # But it may appear in partial_tree_routes (diagnostic preservation).
        assert "NET1" in compiled.partial_tree_routes


# =========================================================================
# PBT — no false completion
# =========================================================================


class TestTruthfulCompletionPBT:
    """Property-based: completion metrics are never inflated by incomplete nets."""

    @given(
        st.integers(min_value=0, max_value=5),  # routed count
        st.integers(min_value=0, max_value=5),  # incomplete count
        st.integers(min_value=0, max_value=3),  # plane count
        st.integers(min_value=0, max_value=2),  # failed count
    )
    @settings(
        max_examples=50,
        deadline=2000,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_success_count_matches_connectivity_dispositions(
        self, routed: int, incomplete: int, plane: int, failed: int
    ):
        """success_count must equal routed + plane_connected, nothing else."""
        connectivity: dict[str, NetConnectivity] = {}
        for i in range(routed):
            connectivity[f"ROUTED_{i}"] = NetConnectivity(
                net=f"ROUTED_{i}",
                disposition=NetDisposition.ROUTED,
                connected_pad_count=2,
                total_required_pad_count=2,
                components=(),
                unresolved_islands=(),
            )
        for i in range(incomplete):
            connectivity[f"INC_{i}"] = NetConnectivity(
                net=f"INC_{i}",
                disposition=NetDisposition.INCOMPLETE,
                connected_pad_count=1,
                total_required_pad_count=3,
                components=(),
                unresolved_islands=(),
            )
        for i in range(plane):
            connectivity[f"PLANE_{i}"] = NetConnectivity(
                net=f"PLANE_{i}",
                disposition=NetDisposition.PLANE_CONNECTED,
                connected_pad_count=5,
                total_required_pad_count=5,
                components=(),
                unresolved_islands=(),
            )
        for i in range(failed):
            connectivity[f"FAIL_{i}"] = NetConnectivity(
                net=f"FAIL_{i}",
                disposition=NetDisposition.FAILED,
                connected_pad_count=0,
                total_required_pad_count=2,
                components=(),
                unresolved_islands=(),
            )
        # Dummy paths — U3 must NOT use their count
        dummy = dict.fromkeys(connectivity)  # type: ignore
        rr = RoutingResults(compiled_routes=dummy, failed_nets=[], connectivity=connectivity)

        assert rr.success_count == routed + plane
        assert rr.failure_count == incomplete + failed, (
            f"incomplete={incomplete}, failed={failed}, but failure_count={rr.failure_count}"
        )
