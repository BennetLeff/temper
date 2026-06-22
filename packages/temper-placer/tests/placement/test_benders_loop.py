"""Tests for benders_loop placement module."""

from pathlib import Path

import pytest

from temper_placer.core.board import Board, Zone
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.placement.benders_loop import (
    BendersPlacementResult,
    benders_placement,
    _extract_board,
    _extract_netlist,
)
from temper_placer.router_v6.stage0_data import (
    DesignRules,
    LayerInfo,
    NetClassRules,
    ParsedPCB,
    StackupInfo,
)


def _make_parsed_pcb(components, nets, board, source_path=None):
    """Helper to construct a minimal ParsedPCB for testing."""
    return ParsedPCB(
        components=components,
        nets=nets,
        zones=[],
        board=board,
        design_rules=DesignRules(
            net_classes={},
            net_class_assignments={},
            default_clearance_mm=0.2,
            default_trace_width_mm=0.25,
            default_via_diameter_mm=0.8,
            default_via_drill_mm=0.4,
        ),
        stackup=StackupInfo(
            layers=[LayerInfo(0, "F.Cu", "signal", 35.0), LayerInfo(1, "B.Cu", "signal", 35.0)],
            total_thickness_mm=1.6,
            layer_count=2,
        ),
        source_path=Path(source_path) if source_path else Path("test.kicad_pcb"),
    )


def _make_test_components():
    """Create test components matching HalfBridgeTemplate refs."""
    return [
        Component(ref="Q1", footprint="TO-247", bounds=(16.0, 21.0), pins=[
            Pin("C", "1", (-5.0, 8.0)), Pin("G", "2", (0.0, -8.0)), Pin("E", "3", (5.0, 8.0)),
        ]),
        Component(ref="Q2", footprint="TO-247", bounds=(16.0, 21.0), pins=[
            Pin("C", "1", (-5.0, 8.0)), Pin("G", "2", (0.0, -8.0)), Pin("E", "3", (5.0, 8.0)),
        ]),
        Component(ref="D1", footprint="TO-247", bounds=(16.0, 21.0), pins=[
            Pin("A", "1", (-5.0, 0.0)), Pin("K", "2", (5.0, 0.0)),
        ]),
        Component(ref="D2", footprint="TO-247", bounds=(16.0, 21.0), pins=[
            Pin("A", "1", (-5.0, 0.0)), Pin("K", "2", (5.0, 0.0)),
        ]),
        Component(ref="C_BUS1", footprint="CAP", bounds=(10.0, 15.0), pins=[
            Pin("1", "1", (-3.0, 0.0)), Pin("2", "2", (3.0, 0.0)),
        ]),
        Component(ref="C_BUS2", footprint="CAP", bounds=(10.0, 15.0), pins=[
            Pin("1", "1", (-3.0, 0.0)), Pin("2", "2", (3.0, 0.0)),
        ]),
    ]


def _make_test_board():
    """Create a test board with a power_zone."""
    return Board(
        width=200.0,
        height=150.0,
        origin=(0.0, 0.0),
        zones=[Zone("power_zone", (50, 25, 150, 125))],
    )


class TestBendersPlacementResult:
    def test_defaults(self):
        result = BendersPlacementResult()
        assert result.placements == {}
        assert result.iterations == 0
        assert result.cuts == 0

    def test_custom_values(self):
        result = BendersPlacementResult(
            placements={"U1": (10.0, 20.0)},
            iterations=5,
            cuts=3,
        )
        assert result.placements == {"U1": (10.0, 20.0)}
        assert result.iterations == 5
        assert result.cuts == 3


class TestBendersPlacementHappyPath:
    def test_template_strategy_returns_result(self):
        components = _make_test_components()
        nets = [
            Net(name="NET1", pins=[("Q1", "C"), ("Q2", "C")]),
            Net(name="NET2", pins=[("D1", "A"), ("D2", "K")]),
            Net(name="NET3", pins=[("C_BUS1", "1"), ("C_BUS2", "2")]),
        ]
        board = _make_test_board()
        parsed = _make_parsed_pcb(components, nets, board)

        result = benders_placement(parsed, 42)

        assert isinstance(result, BendersPlacementResult)
        assert len(result.placements) > 0
        assert result.iterations == 1
        assert result.cuts == 0

    def test_placements_match_placed_refs(self):
        components = _make_test_components()
        nets = []
        board = _make_test_board()
        parsed = _make_parsed_pcb(components, nets, board)

        result = benders_placement(parsed, 42)

        for ref in result.placements:
            x, y = result.placements[ref]
            assert isinstance(x, float)
            assert isinstance(y, float)

    def test_placements_in_zone_bounds(self):
        components = _make_test_components()
        nets = []
        board = _make_test_board()
        parsed = _make_parsed_pcb(components, nets, board)

        result = benders_placement(parsed, 42)
        zone = board.zones[0]

        for ref, (x, y) in result.placements.items():
            assert zone.bounds[0] <= x <= zone.bounds[2], f"{ref} x={x} outside zone"
            assert zone.bounds[1] <= y <= zone.bounds[3], f"{ref} y={y} outside zone"


class TestStrategySelection:
    def test_default_strategy_is_template(self):
        components = _make_test_components()
        nets = []
        board = _make_test_board()
        parsed = _make_parsed_pcb(components, nets, board)

        result = benders_placement(parsed, 42)

        assert isinstance(result, BendersPlacementResult)
        assert result.iterations == 1

    def test_explicit_template_strategy(self):
        components = _make_test_components()
        nets = []
        board = _make_test_board()
        parsed = _make_parsed_pcb(components, nets, board)

        result = benders_placement(parsed, 42, strategy="template")

        assert len(result.placements) > 0
        assert result.iterations == 1

    def test_unknown_strategy_returns_empty(self, caplog):
        components = _make_test_components()
        nets = []
        board = _make_test_board()
        parsed = _make_parsed_pcb(components, nets, board)

        with caplog.at_level("WARNING"):
            result = benders_placement(parsed, 42, strategy="benders")

        assert result.placements == {}
        assert result.iterations == 0
        assert result.cuts == 0
        assert "Unknown placement strategy" in caplog.text


class TestErrorHandling:
    def test_missing_board_raises_value_error(self):
        components = _make_test_components()
        nets = []
        parsed = _make_parsed_pcb(components, nets, None)

        with pytest.raises(ValueError, match="netlist and board data"):
            benders_placement(parsed, 42)

    def test_missing_components_raises_value_error(self):
        board = _make_test_board()
        parsed = _make_parsed_pcb(None, [], board)

        with pytest.raises(ValueError, match="netlist and board data"):
            benders_placement(parsed, 42)


class TestHelpers:
    def test_extract_netlist(self):
        components = _make_test_components()
        nets = [Net(name="N1", pins=[])]
        board = _make_test_board()
        parsed = _make_parsed_pcb(components, nets, board)

        netlist = _extract_netlist(parsed)
        assert isinstance(netlist, Netlist)
        assert netlist.n_components == 6
        assert netlist.n_nets == 1

    def test_extract_board(self):
        board = _make_test_board()
        parsed = _make_parsed_pcb([], [], board)

        extracted = _extract_board(parsed)
        assert extracted is board

    def test_extract_netlist_none_when_missing(self):
        parsed = _make_parsed_pcb(None, None, _make_test_board())

        netlist = _extract_netlist(parsed)
        assert netlist is None
