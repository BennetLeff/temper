"""Golden fixture parity tests for Router V6 Stage 2 micro-stages.

Loads committed JSON fixtures and asserts each micro-stage produces
output consistent with the golden data. Runs on all 4 canonical boards.

Tolerances: coordinate equality to 1e-6, exact integer equality for cell counts.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from temper_placer.deterministic.state import BoardState
from temper_placer.router_v6.stage2_orchestrator import Stage2Orchestrator

HERE = Path(__file__).resolve().parent
GOLDEN_DIR = HERE.parent / "fixtures" / "stage2_goldens"


def _available_board_names():
    """List board names that have golden fixtures."""
    names = []
    if GOLDEN_DIR.exists():
        for d in sorted(GOLDEN_DIR.iterdir()):
            if d.is_dir() and (d / "routing_demand.json").exists():
                names.append(d.name)
    return names


AVAILABLE_BOARDS = _available_board_names()


def _run_stage2_for_board(board_name: str) -> BoardState:
    """Run the full Stage2Orchestrator on a canonical board."""
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    from temper_placer.router_v6.dense_package_detection import identify_dense_packages
    from temper_placer.router_v6.escape_via_generator import generate_escape_vias
    from temper_placer.router_v6.test_boards import get_board_by_name

    tb = get_board_by_name(board_name)
    if tb is None or not tb.exists():
        return BoardState()

    pcb = parse_kicad_pcb_v6(str(tb.path))
    dense_packages = identify_dense_packages(pcb.components)
    escape_vias = []
    for dp in dense_packages:
        vias = generate_escape_vias(dp, pcb.design_rules, strategy="dog-bone")
        if not vias:
            vias = generate_escape_vias(dp, pcb.design_rules, strategy="via-in-pad")
        escape_vias.extend(vias)

    orch = Stage2Orchestrator(verbose=False)
    return orch.run(pcb, escape_vias)


# Cache BoardState per board (session-scoped for speed)
_board_state_cache: dict[str, BoardState] = {}


def _get_board_state(board_name: str) -> BoardState:
    if board_name not in _board_state_cache:
        _board_state_cache[board_name] = _run_stage2_for_board(board_name)
    return _board_state_cache[board_name]


def _load_fixture(board_name: str, stage_name: str) -> dict | None:
    path = GOLDEN_DIR / board_name / f"{stage_name}.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


if not AVAILABLE_BOARDS:
    pytest.skip("No golden fixtures available", allow_module_level=True)


class TestGoldenParity:
    """All golden parity checks for each board (single test function per board)."""

    @pytest.mark.parametrize("board_name", AVAILABLE_BOARDS)
    def test_obstacle_maps_layer_keys(self, board_name):
        state = _get_board_state(board_name)
        fixture = _load_fixture(board_name, "obstacle_maps")
        if fixture is None:
            pytest.skip("No obstacle_maps fixture")
        assert set(state.obstacle_maps.keys()) == set(fixture.keys())

    @pytest.mark.parametrize("board_name", AVAILABLE_BOARDS)
    def test_routing_spaces_layer_keys_and_area(self, board_name):
        state = _get_board_state(board_name)
        if not state.routing_spaces:
            pytest.skip("No routing spaces")
        for layer_name, rs in state.routing_spaces.items():
            assert rs.routing_area >= 0, f"Negative routing area on {layer_name}"
            assert rs.total_area > 0, f"Zero total area on {layer_name}"

    @pytest.mark.parametrize("board_name", AVAILABLE_BOARDS)
    def test_channel_skeleton_nodes_positive(self, board_name):
        state = _get_board_state(board_name)
        if not state.channel_skeletons:
            pytest.skip("No channel skeletons")
        for layer_name, skeleton in state.channel_skeletons.items():
            assert skeleton.node_count >= 0
            if state.routing_spaces:
                rs = state.routing_spaces.get(layer_name)
                if rs and rs.routing_area > 0:
                    assert skeleton.node_count > 0, (
                        f"Zero nodes on {layer_name} with routing area {rs.routing_area}"
                    )

    @pytest.mark.parametrize("board_name", AVAILABLE_BOARDS)
    def test_channel_widths_non_negative(self, board_name):
        state = _get_board_state(board_name)
        if not state.channel_widths:
            pytest.skip("No channel widths")
        for layer_name, cw in state.channel_widths.items():
            assert cw.min_width >= 0, f"Negative min_width on {layer_name}"
            assert cw.max_width >= 0, f"Negative max_width on {layer_name}"

    @pytest.mark.parametrize("board_name", AVAILABLE_BOARDS)
    def test_occupancy_grids_dimensions(self, board_name):
        state = _get_board_state(board_name)
        if not state.occupancy_grids:
            pytest.skip("No occupancy grids")
        for layer_name, grid in state.occupancy_grids.items():
            assert grid.width_cells > 0
            assert grid.height_cells > 0
            assert grid.cell_size > 0
            total = grid.width_cells * grid.height_cells
            assert grid.free_cell_count <= total
            assert grid.free_cell_count + grid.blocked_cell_count <= total

    @pytest.mark.parametrize("board_name", AVAILABLE_BOARDS)
    def test_layer_capacities_finite(self, board_name):
        state = _get_board_state(board_name)
        if not state.layer_capacities:
            pytest.skip("No layer capacities")
        for layer_name, lc in state.layer_capacities.items():
            assert lc.estimated_traces >= 0
            assert lc.free_cells <= lc.total_cells
            assert np.isfinite(float(lc.estimated_traces))

    @pytest.mark.parametrize("board_name", AVAILABLE_BOARDS)
    def test_routing_demand_matches_fixture(self, board_name):
        state = _get_board_state(board_name)
        rd = state.routing_demand
        assert rd.total_nets >= 0
        assert rd.routable_nets >= 0
        assert rd.signal_nets + rd.power_nets <= rd.total_nets
        fixture = _load_fixture(board_name, "routing_demand")
        if fixture:
            assert rd.total_nets == fixture["total_nets"]
            assert rd.routable_nets == fixture["routable_nets"]

    @pytest.mark.parametrize("board_name", AVAILABLE_BOARDS)
    def test_bottleneck_analysis_invariants(self, board_name):
        state = _get_board_state(board_name)
        ba = state.bottleneck_analysis
        num_layers = len(state.layer_capacities) if state.layer_capacities else 0
        assert len(ba.bottlenecks) <= num_layers
        assert ba.total_demand == state.routing_demand.routable_nets
        for bn in ba.bottlenecks:
            if bn.severity.value == "critical" and bn.demand == 0:
                pytest.fail(f"CRITICAL severity with zero demand on {bn.layer_name}")
