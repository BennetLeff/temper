"""Tests for Hypothesis PBT validation and golden fixture infrastructure."""

import json
from pathlib import Path

import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.deterministic import create_legacy_pipeline
from temper_placer.deterministic.state import BoardState

FIXTURE_DIR = Path(__file__).parent.parent / "src" / "temper_placer" / "profiling" / "validation" / "fixtures"


def _make_test_board_state() -> BoardState:
    board = Board(width=100.0, height=80.0, origin=(0.0, 0.0))
    components = [
        Component(
            ref="C1",
            footprint="0805",
            bounds=(5.0, 3.0),
            pins=[
                Pin("1", "1", (0.0, 0.0), net="NET1"),
                Pin("2", "2", (0.0, 0.0), net="GND"),
            ],
            net_class="Signal",
            initial_position=(20.0, 40.0),
        ),
        Component(
            ref="C2",
            footprint="0805",
            bounds=(5.0, 3.0),
            pins=[
                Pin("1", "1", (0.0, 0.0), net="NET2"),
                Pin("2", "2", (0.0, 0.0), net="GND"),
            ],
            net_class="Signal",
            initial_position=(50.0, 40.0),
        ),
        Component(
            ref="C3",
            footprint="0805",
            bounds=(5.0, 3.0),
            pins=[
                Pin("1", "1", (0.0, 0.0), net="NET3"),
                Pin("2", "2", (0.0, 0.0), net="GND"),
            ],
            net_class="Signal",
            initial_position=(80.0, 40.0),
        ),
    ]
    nets = [
        Net(name="NET1", pins=[("C1", "1")], net_class="Signal", weight=1.0),
        Net(name="NET2", pins=[("C2", "1")], net_class="Signal", weight=1.0),
        Net(name="NET3", pins=[("C3", "1")], net_class="Signal", weight=1.0),
        Net(name="GND", pins=[("C1", "2"), ("C2", "2"), ("C3", "2")], net_class="Signal", weight=1.0),
    ]
    netlist = Netlist(components=components, nets=nets)
    return BoardState(board=board, netlist=netlist)


def _serialize_state(state: BoardState) -> dict:
    return {
        "route_count": len(state.routes),
        "via_count": len(state.vias),
        "failed_nets": list(state.failed_nets) if state.failed_nets else [],
        "net_count": len(state.netlist.nets) if state.netlist else 0,
    }


class TestHypothesisInvariants:
    def test_import_invariants(self):
        from temper_placer.profiling.validation.invariants import (
            test_boundary_containment,
            test_determinism,
            test_net_conservation,
            test_pipeline_runs_without_crash,
        )
        assert callable(test_boundary_containment)
        assert callable(test_determinism)
        assert callable(test_net_conservation)
        assert callable(test_pipeline_runs_without_crash)

    def test_deterministic_output_consistent(self):
        state = _make_test_board_state()
        pipeline1 = create_legacy_pipeline()
        r1 = pipeline1.run(state)
        pipeline2 = create_legacy_pipeline()
        r2 = pipeline2.run(state)
        assert _serialize_state(r1) == _serialize_state(r2)
        assert r1.board is not None
        assert r1.netlist is not None

    def test_no_crash_empty_board(self):
        board = Board(width=50.0, height=50.0)
        netlist = Netlist(components=[], nets=[])
        state = BoardState(board=board, netlist=netlist)
        pipeline = create_legacy_pipeline()
        result = pipeline.run(state)
        assert result is not None
        assert result.board is not None

    def test_net_conservation_pbt(self):
        state = _make_test_board_state()
        pipeline = create_legacy_pipeline()
        result = pipeline.run(state)
        assert result.netlist is not None
        input_net_count = len(state.netlist.nets)
        output_net_count = len(result.netlist.nets)
        assert output_net_count == input_net_count

    def test_boundary_containment_pbt(self):
        state = _make_test_board_state()
        pipeline = create_legacy_pipeline()
        result = pipeline.run(state)
        assert result.board is not None
        board = result.board
        for route in result.routes:
            if hasattr(route, 'coordinates'):
                for coord in route.coordinates:
                    assert 0.0 <= coord[0] <= board.width
                    assert 0.0 <= coord[1] <= board.height
        assert result.netlist is not None



class TestGoldenFixtures:
    INPUT_FIXTURE = FIXTURE_DIR / "piantor_left_input.json"
    GOLDEN_FIXTURE = FIXTURE_DIR / "piantor_left_golden.json"

    def test_fixture_directory_exists(self):
        assert FIXTURE_DIR.is_dir(), f"Fixture directory not found at {FIXTURE_DIR}"

    def test_regenerate_and_validate_golden(self):
        state = _make_test_board_state()
        output = _serialize_state(create_legacy_pipeline().run(state))

        if not self.GOLDEN_FIXTURE.exists():
            self.GOLDEN_FIXTURE.parent.mkdir(parents=True, exist_ok=True)
            with open(self.INPUT_FIXTURE, "w") as f:
                json.dump({"board_width": 100.0, "board_height": 80.0}, f)
            with open(self.GOLDEN_FIXTURE, "w") as f:
                json.dump(output, f, indent=2)

        assert self.GOLDEN_FIXTURE.exists(), "Golden fixture not found"
        with open(self.GOLDEN_FIXTURE) as f:
            golden = json.load(f)

        assert output["route_count"] == golden["route_count"]
        assert output["via_count"] == golden["via_count"]
        assert sorted(output.get("failed_nets", [])) == sorted(golden.get("failed_nets", []))
        assert output["net_count"] == golden["net_count"]

    def test_golden_mismatch_detected(self):
        state = _make_test_board_state()
        output = _serialize_state(create_legacy_pipeline().run(state))

        if not self.GOLDEN_FIXTURE.exists():
            pytest.skip("Golden fixture not yet generated")

        with open(self.GOLDEN_FIXTURE) as f:
            golden = json.load(f)

        assert output["route_count"] == golden["route_count"], (
            f"Route count mismatch: {output['route_count']} != {golden['route_count']}"
        )
        assert output["via_count"] == golden["via_count"]
        assert output["net_count"] == golden["net_count"]
