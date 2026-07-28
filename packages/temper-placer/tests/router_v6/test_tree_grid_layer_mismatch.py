# @req(APC1, R3): all-pad routing connectivity — truthful completion reporting
# @req(APC1, R4): completion derived from connectivity, not path count

"""Regression: pad layers the router holds no occupancy grid for.

The tree executor picked a routing layer purely from the two terminals'
``layer_names`` and then indexed ``grids[route_layer]``.  On a board whose
outer layers carry copper pours, ``_parse_board.py`` classifies F.Cu/B.Cu as
``plane``; ``routing_space.py`` builds routing spaces only for ``signal``/
``mixed`` layers, so the only occupancy grids are the inner ones.  An SMD
terminal still — correctly — declares ``("F.Cu",)``, so the lookup blew up
with ``KeyError: 'F.Cu'`` and took the whole route down.

Two properties are pinned here:

1.  The mismatch is *reported*, with a diagnostic naming the pad layers and
    the grid layers, never raised as a bare ``KeyError`` and never routed on
    some other layer the pads do not touch.
2.  The grid filter cannot swallow routable work: whenever a shared layer
    does have a grid, that layer is still chosen.  This is what keeps the
    guard from being a completion-lowering mask.

Measured on ``pcb/temper.kicad_pcb`` (all-pad-tree + zone pours), routing the
rejected edges on an arbitrary grid-backed layer instead reported completion
41.6% vs 26.3% while emitting 23,605 extra segments and leaving KiCad DRC
*worse*: 398 unconnected items vs 396.  The extra completion is not real.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from temper_placer.router_v6._pipeline_route import select_routing_grids
from temper_placer.router_v6.astar_pathfinding import run_astar_pathfinding
from temper_placer.router_v6.channel_mapping import ChannelMapping, ChannelPath
from temper_placer.router_v6.connectivity import NetDisposition, PadIdentity
from temper_placer.router_v6.constraints_geometry import Point
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.terminal_extraction import ParsedTerminal
from temper_placer.router_v6.terminal_tree import TerminalTreeEdge, TerminalTreePlan
from temper_placer.router_v6.terminal_tree_execution import (
    NO_ROUTABLE_LAYER,
    NO_SHARED_LAYER,
    _pick_route_layer,
    execute_terminal_tree,
)

_INNER_LAYERS = ("In1.Cu", "In2.Cu")


def _grids(*layers: str, size: int = 40) -> dict[str, OccupancyGrid]:
    """Occupancy grids for *layers* only — every cell free."""
    return {
        layer: OccupancyGrid(
            layer_name=layer,
            grid=np.zeros((size, size), dtype=np.int8),
            origin=(0.0, 0.0),
            cell_size=1.0,
            width_cells=size,
            height_cells=size,
        )
        for layer in layers
    }


def _terminal(pad: str, x: float, y: float, layers: tuple[str, ...]) -> object:
    return SimpleNamespace(
        identity=PadIdentity("U1", pad, "SIG", x, y, tuple(range(len(layers)))),
        center=SimpleNamespace(x=x, y=y),
        layer_names=layers,
    )


def _two_pad_plan(source: object, target: object) -> TerminalTreePlan:
    return TerminalTreePlan(
        root=source.identity,
        edges=(TerminalTreeEdge(source.identity, target.identity),),
    )


class TestPadLayerWithoutGrid:
    """The F.Cu-pads / inner-layer-grids case that crashed the router."""

    def test_smd_pads_on_a_layer_with_no_grid_are_reported_not_raised(self):
        grids = _grids(*_INNER_LAYERS)
        source = _terminal("1", 2.0, 2.0, ("F.Cu",))
        target = _terminal("2", 20.0, 20.0, ("F.Cu",))

        result = execute_terminal_tree(
            _two_pad_plan(source, target),
            pads=[source, target],
            grid=grids,
            net_id=3,
            trace_width=0.2,
            clearance=0.15,
        )

        assert result.disposition is NetDisposition.INCOMPLETE
        assert len(result.failed_edges) == 1
        reason = result.failure_reasons[result.failed_edges[0]]
        assert reason.startswith(NO_ROUTABLE_LAYER)
        # The diagnostic must name both sides of the mismatch, otherwise this
        # is indistinguishable from ordinary congestion.
        assert "F.Cu" in reason
        assert "In1.Cu" in reason and "In2.Cu" in reason

    def test_rejected_edge_reserves_no_copper_on_any_grid(self):
        """No fabrication: a rejected edge must not mark a grid it cannot use."""
        grids = _grids(*_INNER_LAYERS)
        source = _terminal("1", 2.0, 2.0, ("F.Cu",))
        target = _terminal("2", 20.0, 20.0, ("F.Cu",))

        execute_terminal_tree(
            _two_pad_plan(source, target),
            pads=[source, target],
            grid=grids,
            net_id=3,
            trace_width=0.2,
            clearance=0.15,
        )

        for layer, grid in grids.items():
            assert int(grid.grid.sum()) == 0, f"copper reserved on {layer} for a rejected edge"

    def test_disjoint_pad_layers_report_a_different_cause(self):
        """No shared layer at all is a geometry gap, not a missing grid."""
        grids = _grids(*_INNER_LAYERS)
        source = _terminal("1", 2.0, 2.0, ("In1.Cu",))
        target = _terminal("2", 20.0, 20.0, ("In2.Cu",))

        result = execute_terminal_tree(
            _two_pad_plan(source, target),
            pads=[source, target],
            grid=grids,
            net_id=3,
            trace_width=0.2,
            clearance=0.15,
        )

        assert result.disposition is NetDisposition.INCOMPLETE
        reason = result.failure_reasons[result.failed_edges[0]]
        assert reason.startswith(NO_SHARED_LAYER)

    def test_run_astar_pathfinding_survives_pad_grid_layer_mismatch(self):
        """End-to-end at the crash site (_astar_reconstruct -> executor)."""
        terminals = tuple(
            ParsedTerminal(
                identity=PadIdentity("U1", str(index), "SIG", x, y, (0,)),
                center=Point(x, y),
                layer_names=("F.Cu",),
                is_pth=False,
            )
            for index, (x, y) in enumerate(((2.0, 2.0), (20.0, 2.0), (2.0, 20.0)))
        )
        plan = TerminalTreePlan(
            root=terminals[0].identity,
            edges=(
                TerminalTreeEdge(terminals[0].identity, terminals[1].identity),
                TerminalTreeEdge(terminals[0].identity, terminals[2].identity),
            ),
        )
        channel_path = ChannelPath(
            "SIG",
            [],
            [(2.0, 2.0), (20.0, 2.0), (2.0, 20.0)],
            40.0,
            terminal_tree=plan,
            terminals=terminals,
        )
        grids = _grids(*_INNER_LAYERS)

        result = run_astar_pathfinding(
            ChannelMapping({"SIG": channel_path}),
            grids["In1.Cu"],
            alternate_grid=grids["In2.Cu"],
            enforce_all_pad_tree=True,
        )

        assert "SIG" in result.failed_nets
        assert "SIG" not in result.tree_routes
        assert result.tree_failures["SIG"].reason.startswith(NO_ROUTABLE_LAYER)
        assert result.failure_reports is not None
        assert result.failure_reports["SIG"].failure_reason == NO_ROUTABLE_LAYER


class TestGridFilterPreservesRoutableWork:
    """The guard may only reject layers that have no grid — nothing else."""

    @pytest.mark.parametrize(
        ("source_layers", "target_layers", "expected"),
        [
            # PTH/PTH: both inner layers shared, source declaration order wins.
            (_INNER_LAYERS, _INNER_LAYERS, "In1.Cu"),
            # SMD on a grid-backed layer.
            (("In2.Cu",), ("In2.Cu",), "In2.Cu"),
            # Mixed: the only shared layer that has a grid is still chosen even
            # though the source also declares a grid-less outer layer first.
            (("F.Cu", "In1.Cu"), _INNER_LAYERS, "In1.Cu"),
            (("B.Cu", "In2.Cu"), ("In2.Cu", "B.Cu"), "In2.Cu"),
        ],
    )
    def test_shared_layer_with_a_grid_is_never_rejected(
        self, source_layers, target_layers, expected
    ):
        routable = frozenset(_INNER_LAYERS)
        picked = _pick_route_layer(
            _terminal("1", 0.0, 0.0, source_layers),
            _terminal("2", 5.0, 5.0, target_layers),
            "In1.Cu",
            routable,
        )
        assert picked == expected

    def test_pth_pads_still_route_and_reserve_copper(self):
        grids = _grids(*_INNER_LAYERS)
        source = _terminal("1", 2.0, 2.0, _INNER_LAYERS)
        target = _terminal("2", 20.0, 20.0, _INNER_LAYERS)

        result = execute_terminal_tree(
            _two_pad_plan(source, target),
            pads=[source, target],
            grid=grids,
            net_id=4,
            trace_width=0.2,
            clearance=0.15,
        )

        assert result.disposition is NetDisposition.ROUTED
        assert result.failed_edges == ()
        assert int(grids["In1.Cu"].grid.sum()) > 0
        assert int(grids["In2.Cu"].grid.sum()) == 0

    def test_layerless_terminals_still_use_the_single_grid(self):
        """Synthetic fixtures with no layer_names keep single-grid behaviour."""
        grids = _grids("In1.Cu")
        source = SimpleNamespace(
            identity=PadIdentity("U1", "1", "SIG", 2.0, 2.0, (0,)),
            center=SimpleNamespace(x=2.0, y=2.0),
        )
        target = SimpleNamespace(
            identity=PadIdentity("U1", "2", "SIG", 20.0, 20.0, (0,)),
            center=SimpleNamespace(x=20.0, y=20.0),
        )

        result = execute_terminal_tree(
            _two_pad_plan(source, target),
            pads=[source, target],
            grid=grids,
            net_id=5,
            trace_width=0.2,
            clearance=0.15,
        )

        assert result.disposition is NetDisposition.ROUTED


class TestSelectRoutingGrids:
    """Stage 4 must hand A* two *distinct* layers when two exist."""

    def test_plane_outer_board_keeps_both_inner_layers(self):
        grids = _grids(*_INNER_LAYERS)

        primary, alternate = select_routing_grids(grids)

        assert primary.layer_name == "In1.Cu"
        assert alternate is not None
        assert alternate.layer_name == "In2.Cu", (
            "the second inner layer was dropped — the alternate grid was "
            "selected by excluding the literal 'F.Cu' rather than the "
            "primary grid's actual layer"
        )

    def test_outer_layers_are_still_preferred_when_present(self):
        grids = _grids("F.Cu", "In1.Cu", "B.Cu")

        primary, alternate = select_routing_grids(grids)

        assert primary.layer_name == "F.Cu"
        assert alternate is not None
        assert alternate.layer_name == "B.Cu"

    def test_single_layer_board_has_no_alternate(self):
        primary, alternate = select_routing_grids(_grids("In1.Cu"))

        assert primary.layer_name == "In1.Cu"
        assert alternate is None

    def test_no_grids_at_all_is_an_error(self):
        with pytest.raises(ValueError, match="No occupancy grid"):
            select_routing_grids({})
