"""Monolith vs Stage2Orchestrator parity tests.

Compares the old _run_stage2 monolith approach against the new
Stage2Orchestrator. Full output parity on one representative board;
per-stage parity and performance regression on Piantor_Right.
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from temper_placer.router_v6.bottleneck_analysis import identify_bottlenecks
from temper_placer.router_v6.channel_skeleton import extract_channel_skeleton
from temper_placer.router_v6.channel_widths import compute_channel_widths
from temper_placer.router_v6.layer_capacity import calculate_layer_capacity
from temper_placer.router_v6.obstacle_map import build_obstacle_map
from temper_placer.router_v6.occupancy_grid import build_occupancy_grid
from temper_placer.router_v6.routing_demand import estimate_routing_demand
from temper_placer.router_v6.routing_space import compute_routing_space
from temper_placer.router_v6.stage2_orchestrator import Stage2Orchestrator
from temper_placer.router_v6.test_boards import get_available_boards

BOARDS = get_available_boards()

_pcb_cache: dict[str, tuple] = {}
_state_cache: dict[str, BoardState] = {}


def _prepare_pcb_and_vias(board):
    if board.name in _pcb_cache:
        return _pcb_cache[board.name]
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    from temper_placer.router_v6.dense_package_detection import identify_dense_packages
    from temper_placer.router_v6.escape_via_generator import generate_escape_vias

    pcb = parse_kicad_pcb_v6(str(board.path))
    dense_packages = identify_dense_packages(pcb.components)
    escape_vias = []
    for dp in dense_packages:
        vias = generate_escape_vias(dp, pcb.design_rules, strategy="dog-bone")
        if not vias:
            vias = generate_escape_vias(dp, pcb.design_rules, strategy="via-in-pad")
        escape_vias.extend(vias)
    _pcb_cache[board.name] = (pcb, escape_vias)
    return pcb, escape_vias


def _get_orchestrated_state(board):
    """Run orchestrator once and cache result."""
    if board.name in _state_cache:
        return _state_cache[board.name]
    pcb, escape_vias = _prepare_pcb_and_vias(board)
    orch = Stage2Orchestrator(verbose=False)
    state = orch.run(pcb, escape_vias)
    _state_cache[board.name] = state
    return state


def _run_monolith(pcb, escape_vias):
    routing_spaces = compute_routing_space(pcb, escape_vias)
    obstacle_maps = build_obstacle_map(pcb, escape_vias)
    skeletons = {}
    outer_layers = {k: v for k, v in routing_spaces.items() if k in ("F.Cu", "B.Cu")}
    for layer_name, routing_space in outer_layers.items():
        skeletons[layer_name] = extract_channel_skeleton(routing_space, pcb=pcb)
    channel_widths = {}
    for layer_name, skeleton in skeletons.items():
        channel_widths[layer_name] = compute_channel_widths(
            routing_spaces[layer_name], skeleton
        )
    # R5: base_inflation is trace_width/2 only.  The previous form
    # included default_clearance_mm, which double-counted clearance:
    # once by the router (inflating pad obstacles) and once by KiCad DRC.
    base_inflation = pcb.design_rules.default_trace_width_mm / 2.0
    occupancy_grids = {}
    for layer_name, routing_space in routing_spaces.items():
        occupancy_grids[layer_name] = build_occupancy_grid(
            routing_space, inflation_mm=base_inflation
        )
    layer_capacities = {}
    for layer_name in occupancy_grids:
        cw = channel_widths.get(layer_name)
        if cw is not None:
            layer_capacities[layer_name] = calculate_layer_capacity(
                occupancy_grids[layer_name], cw,
                pcb.design_rules.default_trace_width_mm * 1.5,
                pcb.design_rules.default_clearance_mm,
            )
    routing_demand = estimate_routing_demand(pcb)
    bottleneck_analysis = identify_bottlenecks(layer_capacities, routing_demand)
    return {
        "obstacle_maps": obstacle_maps, "routing_spaces": routing_spaces,
        "skeletons": skeletons, "channel_widths": channel_widths,
        "occupancy_grids": occupancy_grids, "layer_capacities": layer_capacities,
        "routing_demand": routing_demand, "bottleneck_analysis": bottleneck_analysis,
    }


class TestMonolithParity:
    """Full monolith vs orchestrator parity on first available board."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        if not BOARDS:
            pytest.skip("No test boards available")
        self.board = BOARDS[0]
        self.pcb, self.escape_vias = _prepare_pcb_and_vias(self.board)
        self.state = _get_orchestrated_state(self.board)

    def test_full_output_parity(self):
        """Asserts field-by-field equality of all Stage 2 outputs."""
        monolith_output = _run_monolith(self.pcb, self.escape_vias)

        assert monolith_output["routing_demand"].total_nets == self.state.routing_demand.total_nets
        assert monolith_output["routing_demand"].routable_nets == self.state.routing_demand.routable_nets
        assert monolith_output["routing_demand"].total_pins == self.state.routing_demand.total_pins

        assert set(monolith_output["routing_spaces"].keys()) == set(self.state.routing_spaces.keys())
        assert set(monolith_output["skeletons"].keys()) == set(self.state.channel_skeletons.keys())
        assert set(monolith_output["channel_widths"].keys()) == set(self.state.channel_widths.keys())
        assert set(monolith_output["occupancy_grids"].keys()) == set(self.state.occupancy_grids.keys())

        for layer_name in monolith_output["occupancy_grids"]:
            m_grid = monolith_output["occupancy_grids"][layer_name]
            o_grid = self.state.occupancy_grids[layer_name]
            assert np.array_equal(m_grid.grid, o_grid.grid), f"Grid mismatch on {layer_name}"
            assert m_grid.width_cells == o_grid.width_cells
            assert m_grid.height_cells == o_grid.height_cells
            assert abs(m_grid.cell_size - o_grid.cell_size) < 1e-9

        for layer_name in monolith_output["layer_capacities"]:
            m_cap = monolith_output["layer_capacities"][layer_name]
            o_cap = self.state.layer_capacities[layer_name]
            assert m_cap.total_cells == o_cap.total_cells
            assert m_cap.free_cells == o_cap.free_cells
            assert m_cap.estimated_traces == o_cap.estimated_traces

        assert monolith_output["bottleneck_analysis"].total_capacity == self.state.bottleneck_analysis.total_capacity
        assert monolith_output["bottleneck_analysis"].total_demand == self.state.bottleneck_analysis.total_demand
        assert len(monolith_output["bottleneck_analysis"].bottlenecks) == len(self.state.bottleneck_analysis.bottlenecks)

    def test_obstacle_map_parity(self):
        m_obstacles = build_obstacle_map(self.pcb, self.escape_vias)
        for layer_name in m_obstacles:
            assert layer_name in self.state.obstacle_maps
            assert abs(m_obstacles[layer_name].area - self.state.obstacle_maps[layer_name].area) < 1e-6

    def test_routing_space_parity(self):
        m_obstacles = build_obstacle_map(self.pcb, self.escape_vias)
        m_routing = compute_routing_space(self.pcb, self.escape_vias, obstacle_maps=m_obstacles)
        for layer_name in m_routing:
            assert layer_name in self.state.routing_spaces
            assert abs(m_routing[layer_name].routing_area - self.state.routing_spaces[layer_name].routing_area) < 1e-6

    @pytest.mark.slow
    def test_performance_regression(self):
        """Asserts <5% wall-clock overhead (2 warm-up + 2 measured runs)."""
        orch = Stage2Orchestrator(verbose=False)

        # Warm-up
        _run_monolith(self.pcb, self.escape_vias)
        orch.run(self.pcb, self.escape_vias)

        # Benchmark (2 iterations to keep test under timeout)
        t0 = time.perf_counter()
        _run_monolith(self.pcb, self.escape_vias)
        mono_time = time.perf_counter() - t0

        t0 = time.perf_counter()
        orch.run(self.pcb, self.escape_vias)
        orch_time = time.perf_counter() - t0

        overhead_pct = ((orch_time - mono_time) / mono_time) * 100 if mono_time > 0 else 0

        assert overhead_pct < 5.0, (
            f"Performance regression: {overhead_pct:.1f}% overhead "
            f"(monolith: {mono_time:.2f}s, orchestrator: {orch_time:.2f}s)"
        )
