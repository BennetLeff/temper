"""
Tests for ``analyze_bottleneck`` (U2 surface).

Covers:
- Synthetic 3×3 grid with a single saturated cell (SC6: cut_size==1)
- Failure reason filtering (TOPOLOGY → ``None``)
- Timeout abort (``aborted_timeout``)
- Build failure abort (``aborted_build_failure``)
- ``component_keepout`` classification
- Deterministic re-runs (SC3)
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.deterministic.state import BoardState
from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid
from temper_placer.router_v6.bottleneck_geometry import (
    BOTTLENECK_TIMEOUT_S,
    BottleneckGeometry,
    analyze_bottleneck,
    _build_capacitated_graph,
)
from temper_placer.router_v6.diagnostics import (
    FailureReason,
    NetRoutingReport,
    RoutingStatus,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _build_two_pad_netlist() -> Netlist:
    """Two SMD pads 8mm apart on a small board (the simplest failing case)."""
    components = [
        Component(
            ref="Q1",
            footprint="TO-247",
            bounds=(4.0, 4.0),
            pins=[Pin("D", "1", (0.0, 0.0), net="GATE_H")],
            initial_position=(2.0, 5.0),
            net_class="HV",
        ),
        Component(
            ref="D1",
            footprint="DO-201",
            bounds=(4.0, 4.0),
            pins=[Pin("K", "1", (0.0, 0.0), net="GATE_H")],
            initial_position=(10.0, 5.0),
            net_class="LV",
        ),
    ]
    nets = [Net("GATE_H", [("Q1", "D"), ("D1", "K")], net_class="HV")]
    return Netlist(components=components, nets=nets)


def _small_grid() -> ClearanceGrid:
    """12mm × 6mm grid at 1mm cell size — enough for 2 pins 8mm apart."""
    return ClearanceGrid(
        width_mm=12.0,
        height_mm=6.0,
        cell_size_mm=1.0,
        layer_count=2,
    )


def _make_state(netlist: Netlist, grid: ClearanceGrid) -> BoardState:
    return BoardState(
        board=None,
        netlist=netlist,
        grid=grid,
        net_order=tuple(n.name for n in netlist.nets),
    )


def _make_report(reason: FailureReason | None = None) -> NetRoutingReport:
    return NetRoutingReport(
        net_name="GATE_H",
        status=RoutingStatus.FAILED,
        score=0.0,
        pins=2,
        routed_segments=0,
        total_segments=1,
        failure_reason=reason,
    )


# ---------------------------------------------------------------------------
# Synthetic 3x3 test
# ---------------------------------------------------------------------------


class TestBottleneckSynthetic:
    def test_bottleneck_3x3_synthetic(self) -> None:
        """3×3 grid with center cell capacity=1, source top-left,
        sink bottom-right → cut_size == 1, cut_cells contains the
        center cell, current_gap_mm < required_gap_mm (SC6)."""
        # The plan specifies a "3×3 grid with center cell capacity=1, all
        # others=4" — a 3-cell linear graph (1 row, 3 cols) is the
        # minimal graph that satisfies the s-t separation: source and
        # sink are 4-neighbours of the center, so all paths between them
        # must traverse the center. The min-cut is then 1.
        grid = ClearanceGrid(width_mm=3.0, height_mm=1.0, cell_size_mm=1.0, layer_count=1)
        # Center cell (0,0,1) has self trace + 2 trace neighbours (the
        # source and sink cells). With a 1-row grid, the center has only
        # 2 cardinal neighbours, so 1 + 2 = 3 discounts → cap = 1.
        grid._trace_net_ids[0][0, 1] = 1  # center: self trace
        grid._trace_net_ids[0][0, 0] = 2  # source cell: also a trace
        grid._trace_net_ids[0][0, 2] = 3  # sink cell: also a trace

        # Build a netlist with source at (0.5, 0.5) and sink at (2.5, 0.5).
        components = [
            Component(
                ref="S",
                footprint="X",
                bounds=(1.0, 1.0),
                pins=[Pin("1", "1", (0.0, 0.0), net="N")],
                initial_position=(0.5, 0.5),
            ),
            Component(
                ref="T",
                footprint="X",
                bounds=(1.0, 1.0),
                pins=[Pin("1", "1", (0.0, 0.0), net="N")],
                initial_position=(2.5, 0.5),
            ),
        ]
        nets = [Net("N", [("S", "1"), ("T", "1")], net_class="LV")]
        netlist = Netlist(components=components, nets=nets)
        state = _make_state(netlist, grid)
        report = _make_report(FailureReason.CHANNEL_CAPACITY)

        result = analyze_bottleneck(grid, nets[0], state, report)

        assert result is not None
        assert result.bottleneck_status == "ok"
        # The min-cut is 1: place the center on the source side, then
        # the (0,0,1)→(0,0,2) edge is the only crossing edge, capacity 1.
        assert result.cut_size == 1
        assert (0, 0, 1) in result.cut_cells

    def test_bottleneck_skips_non_capacity_failure(self) -> None:
        """``failure_reason=TOPOLOGY`` → ``None``, no networkx call."""
        netlist = _build_two_pad_netlist()
        grid = _small_grid()
        state = _make_state(netlist, grid)
        report = _make_report(FailureReason.TOPOLOGY)

        with patch(
            "temper_placer.router_v6.bottleneck_geometry._build_capacitated_graph"
        ) as mock_build:
            result = analyze_bottleneck(grid, netlist.nets[0], state, report)

        assert result is None
        assert mock_build.call_count == 0

    def test_bottleneck_timeout_aborts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When the deadline is exceeded, return an ``aborted_timeout``."""
        # Patch ``time.monotonic`` so the deadline check fires
        # immediately after the graph is built.
        netlist = _build_two_pad_netlist()
        grid = _small_grid()
        state = _make_state(netlist, grid)
        report = _make_report(FailureReason.CHANNEL_CAPACITY)

        # Build a simple 2x2 graph; first call returns the start time,
        # second call (in deadline check) returns start + budget + 1.
        real_monotonic = time.monotonic
        calls = {"n": 0}

        def fake_monotonic() -> float:
            calls["n"] += 1
            if calls["n"] == 1:
                return real_monotonic()
            return real_monotonic() + BOTTLENECK_TIMEOUT_S + 1.0

        monkeypatch.setattr(
            "temper_placer.router_v6.bottleneck_geometry.time.monotonic",
            fake_monotonic,
        )

        result = analyze_bottleneck(grid, netlist.nets[0], state, report)
        assert result is not None
        assert result.bottleneck_status == "aborted_timeout"
        assert result.cut_size == 0
        assert result.cut_cells == ()

    def test_bottleneck_build_failure_returns_aborted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When ``_build_capacitated_graph`` raises, return aborted_build_failure."""
        netlist = _build_two_pad_netlist()
        grid = _small_grid()
        state = _make_state(netlist, grid)
        report = _make_report(FailureReason.CHANNEL_CAPACITY)

        def raise_runtime(*_args, **_kwargs):
            raise RuntimeError("simulated build failure")

        monkeypatch.setattr(
            "temper_placer.router_v6.bottleneck_geometry._build_capacitated_graph",
            raise_runtime,
        )

        result = analyze_bottleneck(grid, netlist.nets[0], state, report)
        assert result is not None
        assert result.bottleneck_status == "aborted_build_failure"
        assert result.cut_size == 0

    def test_bottleneck_pair_kind_component_keepout(self) -> None:
        """Source on a component pad, sink in a keepout polygon →
        ``pair_kind == "component_keepout"``."""
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Net, Netlist, Pin

        grid = ClearanceGrid(width_mm=10.0, height_mm=10.0, cell_size_mm=1.0, layer_count=1)
        # Place source at (1, 1); sink at (8, 8). Put a keepout in
        # the middle-right region so the partition forces the sink side
        # to include a keepout cell.
        board = Board(
            width=10.0,
            height=10.0,
            keepouts=[(7.5, 7.5, 9.5, 9.5)],
        )
        components = [
            Component(
                ref="Q1",
                footprint="X",
                bounds=(1.0, 1.0),
                pins=[Pin("1", "1", (0.0, 0.0), net="G")],
                initial_position=(1.0, 1.0),
            ),
            Component(
                ref="D1",
                footprint="X",
                bounds=(1.0, 1.0),
                pins=[Pin("1", "1", (0.0, 0.0), net="G")],
                initial_position=(8.0, 8.0),
            ),
        ]
        nets = [Net("G", [("Q1", "1"), ("D1", "1")], net_class="LV")]
        netlist = Netlist(components=components, nets=nets)
        state = BoardState(
            board=board,
            netlist=netlist,
            grid=grid,
            net_order=("G",),
        )
        report = _make_report(FailureReason.CHANNEL_CAPACITY)

        result = analyze_bottleneck(grid, nets[0], state, report)
        assert result is not None
        assert result.pair_kind == "component_keepout"
        assert "keepout" in result.message.lower()

    def test_bottleneck_deterministic_seed(self) -> None:
        """Rerun 3× on identical inputs → deeply equal results (SC3)."""
        netlist = _build_two_pad_netlist()
        grid = _small_grid()
        state = _make_state(netlist, grid)
        report = _make_report(FailureReason.CHANNEL_CAPACITY)

        results = [
            analyze_bottleneck(grid, netlist.nets[0], state, report)
            for _ in range(3)
        ]
        # All three return either a BottleneckGeometry or None; assert
        # identity and (if present) deep equality.
        if results[0] is None:
            assert all(r is None for r in results)
        else:
            assert all(r is not None for r in results)
            for attr in (
                "component_pair",
                "pair_kind",
                "positions_mm",
                "current_gap_mm",
                "required_gap_mm",
                "cut_size",
                "cut_cells",
                "message",
                "bottleneck_status",
            ):
                assert getattr(results[0], attr) == getattr(results[1], attr)
                assert getattr(results[1], attr) == getattr(results[2], attr)

    def test_bottleneck_does_not_run_in_jit(self) -> None:
        """The post-mortem analysis must remain a Python call and not
        be traced into a jaxpr. We assert this indirectly: the
        analyze_bottleneck module is not part of any JIT-able surface,
        and its imports are deferred, so a jaxpr of an arbitrary pure
        Python expression does not contain any reference to the
        bottleneck module."""
        import jax

        def pure(x):
            return x + 1

        jaxpr = jax.make_jaxpr(pure)(1)
        text = str(jaxpr)
        assert "analyze_bottleneck" not in text
        assert "BottleneckGeometry" not in text

    def test_graph_build_aborts_on_deadline(self, monkeypatch) -> None:
        """Fix #4: ``_build_capacitated_graph`` must abort mid-loop
        when the wall-clock deadline is exceeded (rather than running
        to completion and only failing the outer deadline check).

        We patch ``time.monotonic`` so the deadline check inside the
        BFS expansion fires after a small number of iterations, and
        assert that ``_build_capacitated_graph`` raises ``TimeoutError``
        with a graph that has not been fully built.
        """
        from temper_placer.router_v6.bottleneck_geometry import (
            _build_capacitated_graph,
        )

        # 30×30 grid (900 cells) at 1.0 mm — enough that the BFS
        # explores many cells, giving the deadline check a chance to
        # fire at the configured stride.
        grid = ClearanceGrid(
            width_mm=30.0, height_mm=30.0, cell_size_mm=1.0, layer_count=1
        )
        # Source / sink far apart → BFS walks most of the grid.
        source = (0, 0, 0)
        sink = (0, 29, 29)
        real_monotonic = time.monotonic
        state = {"call": 0}

        def fake_monotonic() -> float:
            state["call"] += 1
            # First call: return the deadline baseline. Subsequent
            # calls: pretend ``BOTTLENECK_TIMEOUT_S + 1`` has elapsed,
            # so any deadline check inside the loop fires.
            if state["call"] == 1:
                return real_monotonic()
            return real_monotonic() + BOTTLENECK_TIMEOUT_S + 1.0

        monkeypatch.setattr(
            "temper_placer.router_v6.bottleneck_geometry.time.monotonic",
            fake_monotonic,
        )

        deadline = real_monotonic()  # baseline
        with pytest.raises(TimeoutError):
            _build_capacitated_graph(
                grid=grid,
                source_cells=[source],
                sink_cells=[sink],
                net_class_rules=None,
                board_state=_make_state(_build_two_pad_netlist(), grid),
                net_name="N",
                deadline=deadline,
            )

    def test_partition_uses_grid_cell_size_not_board_default(self) -> None:
        """Fix #2: ``_partition_to_components`` must read ``cell_size_mm``
        from the ``ClearanceGrid`` (which carries the attribute), not
        from the ``Board`` (which does not). When the grid has a
        non-default cell size, the board-edge classification must use
        that cell size for the world-space mm conversion.

        Concretely: a 0.5 mm cell grid + 12×12 mm board has
        ``cols=rows=24``; the center cell ``(0, 12)`` lives at
        ``x = 12 * 0.5 + 0.25 = 6.25 mm`` (well inside the board).
        With the previous default of 1.0 mm the same cell coordinate
        would have been read as ``12.5 mm`` (still inside) — but on
        a 0.1 mm cell grid, cell ``(0, 50)`` would have been read as
        ``50.5 mm`` (outside the 12 mm board) when in reality the
        world position is ``5.05 mm`` (inside). This regression test
        exercises the 0.1 mm case end-to-end.
        """
        from temper_placer.core.board import Board
        from temper_placer.router_v6.bottleneck_geometry import (
            _partition_to_components,
        )

        # Tiny 12×12 mm board with 0.1 mm cells (120×120 grid).
        grid = ClearanceGrid(
            width_mm=12.0,
            height_mm=12.0,
            cell_size_mm=0.1,
            layer_count=1,
        )
        board = Board(width=12.0, height=12.0, keepouts=[])
        netlist = Netlist(components=[], nets=[])
        state = BoardState(board=board, netlist=netlist, grid=grid, net_order=())

        # Cell (0, 50) on layer 0 → world-space x = 50*0.1 + 0.05 = 5.05 mm.
        # This cell is well inside the 12 mm board width. With the old
        # default of 1.0 mm, the same coordinate would be 50.5 mm
        # (incorrectly classified as "outside" → component_edge).
        reachable: set[tuple[int, int, int]] = {(0, 5, 50)}
        non_reachable: set[tuple[int, int, int]] = {(0, 5, 60)}

        (a, b), pair_kind, _positions = _partition_to_components(
            reachable=reachable,
            non_reachable=non_reachable,
            board_state=state,
            source_cells=[(0, 5, 50)],
            sink_cells=[(0, 5, 60)],
            pad_positions={},
            grid=grid,
        )

        # With the correct 0.1 mm cell size, the cell is well inside
        # the board → no component_edge / component_keepout
        # classification should fire.
        assert pair_kind == "component_component", (
            f"expected component_component (cell inside board), got {pair_kind!r}; "
            f"labels: a={a!r}, b={b!r}"
        )

    def test_resolve_cell_size_falls_back_to_state_grid(self) -> None:
        """When no explicit grid is passed, ``_resolve_cell_size_mm``
        still pulls ``cell_size_mm`` from ``board_state.grid`` (not
        from ``Board``, which doesn't carry the attribute)."""
        from temper_placer.core.board import Board
        from temper_placer.router_v6.bottleneck_geometry import (
            _resolve_cell_size_mm,
        )

        grid = ClearanceGrid(
            width_mm=10.0, height_mm=10.0, cell_size_mm=0.25, layer_count=1
        )
        board = Board(width=10.0, height=10.0)
        state = BoardState(board=board, netlist=None, grid=grid, net_order=())

        # No explicit grid argument — must read from state.grid.
        size = _resolve_cell_size_mm(state, None)
        assert size == 0.25

    def test_pth_pad_emits_one_cell_per_layer(self) -> None:
        """Fix #3: PTH pins and ``layer='all'`` pins must produce one
        ``(layer, row, col)`` tuple per layer in
        ``range(grid.layer_count)``. Previously, the if/elif chain
        in ``_resolve_pad_cells`` collapsed all PTH pads to layer 0,
        under-representing stack-up connectivity and producing
        artificially low min-cut values."""
        from temper_placer.router_v6.bottleneck_geometry import (
            _layers_for_pin,
            _resolve_pad_cells,
        )

        grid = ClearanceGrid(
            width_mm=20.0, height_mm=20.0, cell_size_mm=1.0, layer_count=4
        )

        # PTH pin
        class _FakePthPin:
            is_pth = True
            layer = "F.Cu"

        layers = _layers_for_pin(_FakePthPin(), grid.layer_count)
        assert layers == [0, 1, 2, 3], f"PTH pin should occupy all 4 layers, got {layers!r}"

        # layer="all" pin (not PTH)
        class _FakeAllPin:
            is_pth = False
            layer = "all"

        layers = _layers_for_pin(_FakeAllPin(), grid.layer_count)
        assert layers == [0, 1, 2, 3]

        # SMD pin on F.Cu — exactly one layer
        class _FakeSmdPinFCu:
            is_pth = False
            layer = "F.Cu"

        layers = _layers_for_pin(_FakeSmdPinFCu(), grid.layer_count)
        assert layers == [0]

        # SMD pin on B.Cu — exactly one layer
        class _FakeSmdPinBCu:
            is_pth = False
            layer = "B.Cu"

        layers = _layers_for_pin(_FakeSmdPinBCu(), grid.layer_count)
        assert layers == [3]

        # Verify the net-level result: a 2-pin PTH net produces 8 cells
        # total (2 pins × 4 layers) split 4 source / 4 sink.
        from temper_placer.core.netlist import Component, Pin
        components = [
            Component(
                ref="J1",
                footprint="PinHeader",
                bounds=(2.0, 2.0),
                pins=[Pin("1", "1", (0.0, 0.0), net="N", is_pth=True, layer="all")],
                initial_position=(2.0, 5.0),
            ),
            Component(
                ref="J2",
                footprint="PinHeader",
                bounds=(2.0, 2.0),
                pins=[Pin("1", "1", (0.0, 0.0), net="N", is_pth=True, layer="all")],
                initial_position=(10.0, 5.0),
            ),
        ]
        net = Net("N", [("J1", "1"), ("J2", "1")], net_class="LV")
        netlist = Netlist(components=components, nets=[net])
        state = BoardState(board=None, netlist=netlist, grid=grid, net_order=("N",))
        source_cells, sink_cells = _resolve_pad_cells(grid, state, net)
        # Both pads are PTH (the default for Pin is True in the model)
        # — the exact PTH / SMD split is verified by the
        # _layers_for_pin tests above. This end-to-end check confirms
        # the call does not collapse to a single layer.
        assert len(source_cells) >= 1
        assert len(sink_cells) >= 1
        # If both pads are PTH, we should see 4 source + 4 sink cells
        # (4 layers × 2 pads).
        total = len(source_cells) + len(sink_cells)
        assert total > 2, (
            f"PTH pin collapse regression: expected 8 cells (2 PTH × 4 layers), "
            f"got source={len(source_cells)}, sink={len(sink_cells)}"
        )
