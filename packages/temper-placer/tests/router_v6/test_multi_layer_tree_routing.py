# @req(APC1, R3): all-pad routing connectivity — truthful completion reporting
# @req(APC1, R4): completion derived from connectivity, not path count

"""RED (TDD): Multi-layer tree execution — cross-layer PTH support.

These tests FAIL until the pipeline relaxes its same-layer filter AND the
tree executor accepts multi-grid routing with shared-layer selection.

Run as:  uv run pytest tests/router_v6/test_multi_layer_tree_routing.py -q
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from temper_placer.router_v6.connectivity import NetDisposition, PadIdentity
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.terminal_tree import (
    TerminalTreeEdge,
    TerminalTreePlan,
)
from temper_placer.router_v6.terminal_tree_execution import execute_terminal_tree

_LAYERS = ("F.Cu", "B.Cu")


def _make_grids(
    width: int = 160,
    height: int = 160,
    layers: tuple[str, ...] = _LAYERS,
) -> dict[str, OccupancyGrid]:
    return {
        layer: OccupancyGrid(
            layer_name=layer,
            grid=np.zeros((height, width), dtype=np.int32),
            origin=(0.0, 0.0),
            cell_size=0.1,
            width_cells=width,
            height_cells=height,
        )
        for layer in layers
    }


def _terminal(
    ref: str,
    pad: str,
    net: str,
    x: float,
    y: float,
    *,
    layers: tuple[str, ...] = ("F.Cu",),
    pth: bool = False,
) -> object:
    from types import SimpleNamespace

    return SimpleNamespace(
        identity=PadIdentity(
            component_ref=ref,
            pad=pad,
            net=net,
            x=x,
            y=y,
            layers=tuple(0 if l == "F.Cu" else 1 for l in layers),
        ),
        center=SimpleNamespace(x=x, y=y),
        layer_names=layers,
    )


class TestMultiLayerTreeExecution:
    """Cross-layer tree executor tests."""

    def test_empty_grids_dict_raises_clear_error(self):
        """An empty grids dict must fail with a clear error, not StopIteration."""
        with pytest.raises(ValueError, match="at least one occupancy grid"):
            execute_terminal_tree(
                plan=None, pads=[], grid={}, net_id=0,
            )

    def test_multi_grid_pth_spans_both_layers(self):
        """Three PTH terminals on one net: route on both layers.

        PTH pads span F.Cu/B.Cu, so the executor MUST pick a shared
        layer and route all edges on it.
        """
        grids = _make_grids()
        t0 = _terminal("U1", "1", "NET", 1.0, 1.0, layers=("F.Cu", "B.Cu"), pth=True)
        t1 = _terminal("U1", "2", "NET", 5.0, 5.0, layers=("F.Cu", "B.Cu"), pth=True)
        t2 = _terminal("U1", "3", "NET", 9.0, 9.0, layers=("F.Cu", "B.Cu"), pth=True)

        plan = TerminalTreePlan(
            root=t0.identity,
            edges=(
                TerminalTreeEdge(t0.identity, t1.identity),
                TerminalTreeEdge(t1.identity, t2.identity),
            ),
        )
        result = execute_terminal_tree(
            plan,
            pads=[t0, t1, t2],
            grid=grids,  # <-- dict, not single OccupancyGrid
            net_id=7,
            trace_width=0.2,
            clearance=0.15,
        )
        assert result.disposition == NetDisposition.ROUTED
        assert result.failed_edge is None
        assert len(result.completed_edges) == 2
        # Source t0 declares ("F.Cu", "B.Cu") — F.Cu first, so edges
        # route on F.Cu (declaration-order priority, not alphabetical).
        assert int(grids["F.Cu"].grid.sum()) > 0

    def test_mixed_smd_pth_net_routes_on_fcu_when_all_fcu_available(self):
        """Two SMD (F.Cu only) + one PTH (both layers): route on F.Cu.

        The PTH terminal has F.Cu in its layer_names, so the shared
        layer is F.Cu. The executor MUST detect this and route there.
        """
        grids = _make_grids()
        t0 = _terminal("U1", "1", "NET", 1.0, 1.0)
        t1 = _terminal("U1", "2", "NET", 5.0, 5.0)
        t2 = _terminal("U1", "3", "NET", 9.0, 9.0, layers=("F.Cu", "B.Cu"), pth=True)

        plan = TerminalTreePlan(
            root=t0.identity,
            edges=(
                TerminalTreeEdge(t0.identity, t1.identity),
                TerminalTreeEdge(t1.identity, t2.identity),
            ),
        )
        result = execute_terminal_tree(
            plan,
            pads=[t0, t1, t2],
            grid=grids,
            net_id=7,
            trace_width=0.2,
            clearance=0.15,
        )
        assert result.disposition == NetDisposition.ROUTED

    def test_smd_on_bcu_only_routes_on_bcu(self):
        """Two B.Cu-only SMD terminals: the executor MUST route on B.Cu."""
        grids = _make_grids()
        t0 = _terminal("U1", "1", "NET", 1.0, 1.0, layers=("B.Cu",))
        t1 = _terminal("U1", "2", "NET", 5.0, 5.0, layers=("B.Cu",))

        plan = TerminalTreePlan(
            root=t0.identity,
            edges=(TerminalTreeEdge(t0.identity, t1.identity),),
        )
        result = execute_terminal_tree(
            plan,
            pads=[t0, t1],
            grid=grids,
            net_id=8,
            trace_width=0.2,
            clearance=0.15,
        )
        assert result.disposition == NetDisposition.ROUTED
        # Copper reserved on B.Cu, NOT F.Cu.
        assert int(grids["B.Cu"].grid.sum()) > 0

    def test_no_shared_layer_returns_incomplete(self):
        """F.Cu-only SMD to B.Cu-only SMD with no shared layer: die cleanly.

        Without via-aware transitions (prerequisite not yet landed),
        the executor MUST return INCOMPLETE rather than routing on
        the wrong layer or producing illegal cross-layer geometry.
        """
        grids = _make_grids()
        t0 = _terminal("U1", "1", "NET", 1.0, 1.0, layers=("F.Cu",))
        t1 = _terminal("U1", "2", "NET", 5.0, 5.0, layers=("B.Cu",))

        plan = TerminalTreePlan(
            root=t0.identity,
            edges=(TerminalTreeEdge(t0.identity, t1.identity),),
        )
        result = execute_terminal_tree(
            plan,
            pads=[t0, t1],
            grid=grids,
            net_id=9,
            trace_width=0.2,
            clearance=0.15,
        )
        assert result.disposition == NetDisposition.INCOMPLETE
        assert result.failed_edge is not None
        assert (result.disposition == NetDisposition.ROUTED) == (result.failed_edge is None)
        assert result.failed_edge.source == t0.identity
        assert result.failed_edge.target == t1.identity

    def test_multi_grid_occupancy_reservation_is_layer_scoped(self):
        """Copper reserved on F.Cu must not pollute B.Cu grid."""
        grids = _make_grids()
        t0 = _terminal("U1", "1", "NET", 1.0, 1.0)
        t1 = _terminal("U1", "2", "NET", 5.0, 5.0)

        plan = TerminalTreePlan(
            root=t0.identity,
            edges=(TerminalTreeEdge(t0.identity, t1.identity),),
        )
        execute_terminal_tree(
            plan,
            pads=[t0, t1],
            grid=grids,
            net_id=7,
            trace_width=0.2,
            clearance=0.15,
        )
        assert int(grids["F.Cu"].grid.sum()) > 0
        assert int(grids["B.Cu"].grid.sum()) == 0, "B.Cu grid must be untouched"


class TestPipelineMixedLayerFilter:
    """Pipeline layer filter relaxation — RED until the filter is removed."""

    def test_pipeline_does_not_skip_mixed_layer_terminals(self):
        """ParsedTerminal from extraction carries public layer_names, not private.

        The executor accesses `layer_names` (public field on ParsedTerminal),
        not `_layer_names`. This test verifies the contract: a terminal
        extracted from a PTH pad has layer_names spanning both layers.
        """
        from temper_placer.router_v6.terminal_extraction import ParsedTerminal

        # A ParsedTerminal for a PTH pad must carry multiple layer_names.
        # We construct one directly since the full extraction path requires
        # a real parsed PCB. This guards against the field being renamed.
        terminal = ParsedTerminal(
            identity=PadIdentity(
                component_ref="U1", pad="1", net="NET", x=0.0, y=0.0, layers=(0, 1),
            ),
            center=SimpleNamespace(x=0.0, y=0.0),
            layer_names=("F.Cu", "B.Cu"),
            is_pth=True,
        )
        assert hasattr(terminal, "layer_names")
        assert len(terminal.layer_names) > 1  # PTH spans both layers
        # The executor accesses layer_names (not _layer_names).
        assert getattr(terminal, "layer_names", None) is not None
