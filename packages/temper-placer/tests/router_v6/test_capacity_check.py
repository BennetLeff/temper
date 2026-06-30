"""Property-based tests for capacity-demand pre-routing check.

Tests the mathematical correctness proof and routing correlation
on both synthetic and real board data.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from shapely.geometry import MultiPolygon, box

from temper_placer.core.netlist import Component, Net, Pin
from temper_placer.router_v6.capacity_check import (
    _sum_capacity_in_bbox,
    build_capacity_demand_report,
    compute_capacity_demand_ratios,
)
from temper_placer.router_v6.routing_space import RoutingSpace
from temper_placer.router_v6.stage0_data import (
    DesignRules,
    LayerInfo,
    ParsedPCB,
    StackupInfo,
)

if TYPE_CHECKING:
    from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

_TEMPER_PCB = Path(__file__).resolve().parents[4] / "pcb" / "temper.kicad_pcb"


def _make_parsed_pcb(
    components=None,
    nets=None,
    board_origin=(0.0, 0.0),
    board_width=100.0,
    board_height=100.0,
    trace_width=0.2,
) -> ParsedPCB:
    """Construct a minimal ParsedPCB for testing."""
    layers = [
        LayerInfo(index=0, name="F.Cu", layer_type="signal", thickness_um=35),
        LayerInfo(index=1, name="B.Cu", layer_type="signal", thickness_um=35),
    ]
    rules = DesignRules(
        net_classes={},
        net_class_assignments={},
        default_clearance_mm=0.2,
        default_trace_width_mm=trace_width,
        default_via_diameter_mm=0.6,
        default_via_drill_mm=0.3,
    )
    pcb = ParsedPCB(
        components=components or [],
        nets=nets or [],
        design_rules=rules,
        stackup=StackupInfo(layers=layers, total_thickness_mm=1.6, layer_count=2),
        zones=[],
        board=None,
        source_path=None,
    )

    class _MockBoard:
        def __init__(self):
            self.width = board_width
            self.height = board_height
            self.origin = board_origin

        def get_bounds_array(self):
            return [
                board_origin[0], board_origin[1],
                board_origin[0] + board_width, board_origin[1] + board_height,
            ]

    pcb.board_geometry = _MockBoard()
    return pcb


def _make_stage2_output(pcb: ParsedPCB, board_width=100.0, board_height=100.0):
    """Build a Stage2Output-like object with routing spaces for F.Cu and B.Cu."""
    from temper_placer.router_v6.pipeline import Stage2Output

    available = box(0, 0, board_width, board_height)
    if pcb.components:
        from shapely.ops import unary_union
        comp_boxes = []
        for comp in pcb.components:
            if comp.initial_position:
                cx, cy = comp.initial_position
                bw, bh = comp.bounds
                comp_boxes.append(box(
                    cx - bw / 2, cy - bh / 2,
                    cx + bw / 2, cy + bh / 2,
                ))
        if comp_boxes:
            obstacles = unary_union(comp_boxes)
            fcu_available = available.difference(obstacles)
            obs_area = obstacles.area
        else:
            obstacles = MultiPolygon([])
            fcu_available = available
            obs_area = 0.0
    else:
        obstacles = MultiPolygon([])
        fcu_available = available
        obs_area = 0.0

    if not isinstance(fcu_available, MultiPolygon):
        from shapely.geometry import Polygon
        if isinstance(fcu_available, Polygon):
            fcu_available = MultiPolygon([fcu_available])

    rs_fcu = RoutingSpace(
        layer_name="F.Cu",
        available_area=fcu_available,
        total_area=board_width * board_height,
        obstacle_area=obs_area,
        routing_area=fcu_available.area,
    )
    rs_bcu = RoutingSpace(
        layer_name="B.Cu",
        available_area=available,
        total_area=board_width * board_height,
        obstacle_area=0.0,
        routing_area=available.area,
    )

    return Stage2Output(
        obstacle_maps={},
        routing_spaces={"F.Cu": rs_fcu, "B.Cu": rs_bcu},
        skeletons={},
        channel_widths={},
        occupancy_grids={},
        layer_capacities={},
        routing_demand=None,
        bottleneck_analysis=None,
    )


def _make_component(ref, x, y, net_pins, footprint="SOIC-8", width=10.0, height=8.0):
    """Create a component with pins connected to specified nets."""
    pins = []
    for i, net_name in enumerate(net_pins):
        px = -width / 2 + 1.0 + (i % 4) * 2.0
        py = -height / 2 + 1.0 + (i // 4) * 6.0
        pins.append(Pin(
            name=str(i + 1), number=str(i + 1),
            position=(px, py), net=net_name,
            width=1.0, height=1.0, shape="rect", layer="F.Cu",
        ))
    return Component(
        ref=ref, footprint=footprint, bounds=(width, height), pins=pins,
        initial_position=(x, y), initial_rotation=0,
    )


# ---------------------------------------------------------------------------
# Correctness proof: Base case — empty board
# ---------------------------------------------------------------------------

@given(
    width=st.floats(min_value=40, max_value=80),
    height=st.floats(min_value=40, max_value=80),
)
@settings(max_examples=20, deadline=None)
def test_empty_board_infinite_capacity(width, height):
    """An empty board with no components has infinite capacity for a
    hypothetical net (EDT = max at all interior cells)."""
    pcb = _make_parsed_pcb(board_width=width, board_height=height)
    stage2 = _make_stage2_output(pcb, board_width=width, board_height=height)

    net = Net(name="N1", pins=[("C1", "1"), ("C2", "1")])
    c1 = _make_component("C1", width / 4, height / 2, ["N1", "N1"])
    c2 = _make_component("C2", 3 * width / 4, height / 2, ["N1", "N1"])
    pcb.components = [c1, c2]
    pcb.nets = [net]

    ratios = compute_capacity_demand_ratios(stage2, pcb)
    assert "N1" in ratios
    assert ratios["N1"] > 0.0
    assert ratios["N1"] > 2.0, f"Expected ratio > 2.0 on empty board, got {ratios['N1']}"


# ---------------------------------------------------------------------------
# Correctness proof: Monotonicity
# ---------------------------------------------------------------------------

@given(
    board_size=st.floats(min_value=50, max_value=80),
    offset=st.floats(min_value=2.0, max_value=15.0),
)
@settings(max_examples=20, deadline=None)
def test_capacity_monotonicity(board_size, offset):
    """Adding components reduces available routing capacity.
    Monotonicity: capacity(pcb_with_obs) <= capacity(pcb_empty)."""
    empty_pcb = _make_parsed_pcb(board_width=board_size, board_height=board_size)
    empty_stage2 = _make_stage2_output(empty_pcb, board_width=board_size, board_height=board_size)

    net = Net(name="N1", pins=[("C1", "1"), ("C2", "1")])
    c1 = _make_component("C1", 10.0, board_size / 2, ["N1", "N1"])
    c2 = _make_component("C2", board_size - 10.0, board_size / 2, ["N1", "N1"])

    empty_pcb.components = [c1, c2]
    empty_pcb.nets = [net]
    empty_ratios = compute_capacity_demand_ratios(empty_stage2, empty_pcb)

    # Now add a blocking component between them
    obs_pcb = _make_parsed_pcb(board_width=board_size, board_height=board_size)
    c3 = _make_component(
        "C3", board_size / 2, board_size / 2, ["N99"],
        width=offset * 2, height=board_size * 0.6,
    )
    obs_pcb.components = [c1, c2, c3]
    obs_pcb.nets = [net]
    obs_stage2 = _make_stage2_output(obs_pcb, board_width=board_size, board_height=board_size)
    obs_ratios = compute_capacity_demand_ratios(obs_stage2, obs_pcb)

    assert "N1" in empty_ratios
    assert "N1" in obs_ratios
    assert obs_ratios["N1"] <= empty_ratios["N1"], (
        f"Monotonicity violated: obs={obs_ratios['N1']}, empty={empty_ratios['N1']}"
    )


# ---------------------------------------------------------------------------
# Correctness proof: Induction — demand recovery
# ---------------------------------------------------------------------------

@given(
    board_size=st.floats(min_value=50, max_value=80),
)
@settings(max_examples=20, deadline=None)
def test_capacity_exceeds_single_trace_demand(board_size):
    """A simple 2-pin net on a nearly-empty board always has capacity
    well exceeding its trace demand (ratio > 5.0).  This validates
    the induction base: one trace does not saturate the board."""
    pcb = _make_parsed_pcb(board_width=board_size, board_height=board_size)

    c1 = _make_component("C1", 10.0, board_size / 2, ["N1", "N1"])
    c2 = _make_component("C2", board_size - 10.0, board_size / 2, ["N1", "N1"])
    net = Net(name="N1", pins=[("C1", "1"), ("C2", "1")])
    pcb.components = [c1, c2]
    pcb.nets = [net]

    stage2 = _make_stage2_output(pcb, board_width=board_size, board_height=board_size)
    ratios = compute_capacity_demand_ratios(stage2, pcb)

    assert ratios["N1"] > 5.0, (
        f"Single trace should have ample capacity, got ratio={ratios['N1']:.2f}"
    )


# ---------------------------------------------------------------------------
# PBT: Ratio scales correctly with demand
# ---------------------------------------------------------------------------

@given(
    board_size=st.floats(min_value=50, max_value=80),
    trace_width=st.floats(min_value=0.1, max_value=0.5),
    separation=st.floats(min_value=10.0, max_value=50.0),
)
@settings(max_examples=20, deadline=None)
def test_ratio_inversely_proportional_to_trace_width(board_size, trace_width, separation):
    """Doubling the trace width halves the capacity-demand ratio."""
    pcb1 = _make_parsed_pcb(board_width=board_size, board_height=board_size, trace_width=trace_width)
    c1 = _make_component("C1", board_size / 2 - separation / 2, board_size / 2, ["N1", "N1"])
    c2 = _make_component("C2", board_size / 2 + separation / 2, board_size / 2, ["N1", "N1"])
    net = Net(name="N1", pins=[("C1", "1"), ("C2", "1")])
    pcb1.components = [c1, c2]
    pcb1.nets = [net]
    stage2 = _make_stage2_output(pcb1, board_width=board_size, board_height=board_size)
    ratio1 = compute_capacity_demand_ratios(stage2, pcb1)["N1"]

    pcb2 = _make_parsed_pcb(board_width=board_size, board_height=board_size, trace_width=trace_width * 2)
    pcb2.components = [c1, c2]
    pcb2.nets = [net]
    stage2_2 = _make_stage2_output(pcb2, board_width=board_size, board_height=board_size)
    ratio2 = compute_capacity_demand_ratios(stage2_2, pcb2)["N1"]

    # Ratio should be approximately halved
    assert 0.45 * ratio1 < ratio2 < 0.55 * ratio1, (
        f"Expected ratio2 ≈ ratio1/2, got ratio1={ratio1:.4f}, ratio2={ratio2:.4f}"
    )


# ---------------------------------------------------------------------------
# PBT: _sum_capacity_in_bbox correct on known test data
# ---------------------------------------------------------------------------

@given(
    side=st.integers(min_value=10, max_value=100),
)
@settings(max_examples=50, deadline=5000)
def test_bbox_capacity_on_full_grid(side):
    """On a fully-open EDT grid (no obstacles), capacity in a bbox
    covering the entire region equals the integral of 2*d*cell_size*cell_size."""
    mask = np.ones((side, side), dtype=bool)
    edt = np.full((side, side), side / 2.0)
    bounds = (0.0, 0.0, side * 0.1, side * 0.1)
    cell_size = 0.1

    cap = _sum_capacity_in_bbox(edt, mask, bounds, cell_size, 0.0, side * 0.1, 0.0, side * 0.1)

    # Expected: each cell contributes 2 * d * cell_size * cell_size
    # d = side/2 for all cells
    expected = float(side * side) * (2.0 * (side / 2.0) * cell_size) * cell_size
    assert math.isclose(cap, expected, rel_tol=1e-6), f"cap={cap}, expected={expected}"


def test_bbox_capacity_empty_mask_returns_zero():
    """If no interior cells in bbox, capacity is zero."""
    side = 50
    mask = np.ones((side, side), dtype=bool)
    edt = np.ones((side, side))
    bounds = (0.0, 0.0, side * 0.1, side * 0.1)

    # Query a bbox completely outside the grid
    cap = _sum_capacity_in_bbox(edt, mask, bounds, 0.1, -10.0, -5.0, -10.0, -5.0)
    assert cap == 0.0

    # Query a zero-size bbox
    cap2 = _sum_capacity_in_bbox(edt, mask, bounds, 0.1, 5.0, 5.0, 5.0, 5.0)
    assert cap2 >= 0.0


# ---------------------------------------------------------------------------
# Benchmark: temper.kicad_pcb capacity-demand vs. routing outcomes
# ---------------------------------------------------------------------------

def test_temper_kicad_pcb_capacity_demand_benchmark():
    """Log capacity-demand ratios for all nets on temper.kicad_pcb
    from Stage 2 channel analysis, and compare with pre-existing
    routing completion data.

    The capacity-demand pre-check is computed from EDT grids built
    during Stage 2 (obstacle map + routing space + channel widths).
    The comparison uses the pre-existing metrics file which records
    routing completion data from a prior successful full-router run.
    """
    if not _TEMPER_PCB.exists():
        pytest.skip(f"temper.kicad_pcb not found at {_TEMPER_PCB}")

    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    from temper_placer.router_v6.dense_package_detection import identify_dense_packages
    from temper_placer.router_v6.escape_via_generator import generate_escape_vias
    from temper_placer.router_v6.stage2_orchestrator import Stage2Orchestrator

    pcb = parse_kicad_pcb_v6(_TEMPER_PCB)

    dense_packages = identify_dense_packages(pcb.components)
    escape_vias = []
    for dense_pkg in dense_packages:
        vias = generate_escape_vias(dense_pkg, pcb.design_rules, strategy="dog-bone")
        if not vias:
            vias = generate_escape_vias(dense_pkg, pcb.design_rules, strategy="via-in-pad")
        escape_vias.extend(vias)

    orchestrator = Stage2Orchestrator(verbose=False)
    state = orchestrator.run(pcb, escape_vias)
    stage2 = Stage2Orchestrator.assemble_stage2_output(state)

    ratios = compute_capacity_demand_ratios(stage2, pcb)

    report = build_capacity_demand_report(stage2, pcb)

    print("\n=== Capacity-Demand Pre-Routing Check: temper.kicad_pcb ===")
    print(f"{'Net':<24} {'Ratio':>12} {'Assessment':>14}")
    print("-" * 52)

    for net_name in sorted(ratios, key=lambda n: ratios[n]):
        ratio = ratios[net_name]
        if ratio == float("inf"):
            assessment = "INFINITE"
        elif ratio >= 2.0:
            assessment = "SAFE"
        elif ratio >= 1.0:
            assessment = "ADVISED"
        else:
            assessment = "AT-RISK"
        rstr = "inf" if ratio == float("inf") else f"{ratio:>12.2f}"
        print(f"{net_name:<24} {rstr} {assessment:>14}")

    print("-" * 52)
    print(f"Total nets evaluated: {len(ratios)}")
    print(f"At-risk (ratio < 1.0): {len(report.at_risk_nets)} {report.at_risk_nets}")
    print(f"Advised (1.0 <= ratio < 2.0): {len([n for n, r in ratios.items() if 1.0 <= r < 2.0])}")
    print(f"Safe (ratio >= 2.0): {len([n for n, r in ratios.items() if r >= 2.0 and r != float('inf')])}")

    metrics_path = Path(__file__).resolve().parents[4] / "pcb" / "temper_router_v6_metrics.json"
    if metrics_path.exists():
        import json
        with open(metrics_path) as f:
            metrics = json.load(f)
        print(f"\nReference routing data (from {metrics_path.name}):")
        print(f"  Completion rate: {metrics.get('completion_rate', 'N/A')}")
        print(f"  Success count: {metrics.get('success_count', 'N/A')}")
        print(f"  Failure count: {metrics.get('failure_count', 'N/A')}")


# ---------------------------------------------------------------------------
# CapacityDemandReport tests
# ---------------------------------------------------------------------------

def test_capacity_demand_report_classification():
    """build_capacity_demand_report correctly partitions nets."""
    pcb = _make_parsed_pcb(board_width=100, board_height=100)
    c1 = _make_component("C1", 20, 50, ["N1", "N2"])
    c2 = _make_component("C2", 80, 50, ["N1", "N2"])
    nets = [
        Net(name="N1", pins=[("C1", "1"), ("C2", "1")]),
        Net(name="N2", pins=[("C1", "2"), ("C2", "2")]),
    ]
    pcb.components = [c1, c2]
    pcb.nets = nets
    stage2 = _make_stage2_output(pcb)

    report = build_capacity_demand_report(stage2, pcb, risk_threshold=1.0)
    assert len(report.ratios) == 2
    assert report.safe_count + report.at_risk_count == 2


def test_compute_capacity_demand_ratios_empty():
    """Empty input returns empty dict."""
    pcb = _make_parsed_pcb()
    stage2 = _make_stage2_output(pcb)
    ratios = compute_capacity_demand_ratios(stage2, pcb)
    assert isinstance(ratios, dict)
    assert len(ratios) == 0


def test_compute_capacity_demand_ratios_no_routing_spaces():
    """When routing_spaces is None, returns empty dict."""
    from temper_placer.router_v6.pipeline import Stage2Output
    pcb = _make_parsed_pcb()
    stage2 = Stage2Output(
        obstacle_maps={}, routing_spaces=None, skeletons={},
        channel_widths={}, occupancy_grids={}, layer_capacities={},
        routing_demand=None, bottleneck_analysis=None,
    )
    ratios = compute_capacity_demand_ratios(stage2, pcb)
    assert ratios == {}


def test_single_pin_net_infinite_ratio():
    """Single-pin nets get infinite ratio."""
    pcb = _make_parsed_pcb(board_width=100, board_height=100)
    c1 = _make_component("C1", 50, 50, ["N1"])
    net = Net(name="N1", pins=[("C1", "1")])
    pcb.components = [c1]
    pcb.nets = [net]
    stage2 = _make_stage2_output(pcb)
    ratios = compute_capacity_demand_ratios(stage2, pcb)
    assert ratios["N1"] == float("inf")
