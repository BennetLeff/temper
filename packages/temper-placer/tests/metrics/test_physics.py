import numpy as np
import pytest

from temper_placer.core.board import Board, Zone
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.core.state import PlacementState
from temper_placer.metrics.physics import (
    measure_emi,
    measure_geometric,
    measure_routability,
    measure_thermal,
)
from temper_placer.physics.inductance import estimate_loop_inductance


@pytest.fixture
def sample_setup():
    board = Board(width=100, height=100, zones=[Zone("Z1", (0, 0, 50, 50))])

    c1 = Component("U1", "Pkg1", (10, 10), zone="Z1", pins=[Pin("1", "1", (3.0, 0.0))])
    c2 = Component("U2", "Pkg2", (10, 10), pins=[Pin("1", "1", (-3.0, 0.0))])
    netlist = Netlist([c1, c2], [Net("N1", [("U1", "1"), ("U2", "1")])])

    # U1 at (25, 25) - in zone Z1
    # U2 at (25, 30) - overlapping with U1
    positions = np.array([[25.0, 25.0], [25.0, 30.0]])
    state = PlacementState.from_positions(positions)

    return board, netlist, state

def test_measure_geometric(sample_setup):
    board, netlist, state = sample_setup
    metrics = measure_geometric(state, netlist, board)

    assert metrics.overlap_count == 1
    assert metrics.overlap_area_mm2 > 0
    assert metrics.zone_violation_count == 0 # U1 is in Z1

    # Move U1 out of zone
    state.positions[0] = [75.0, 75.0]
    metrics = measure_geometric(state, netlist, board)
    assert metrics.zone_violation_count == 1

def test_measure_emi(sample_setup):
    board, netlist, state = sample_setup
    # Create a 3-component loop
    c3 = Component("U3", "Pkg3", (10, 10))
    netlist.components.append(c3)
    netlist.build_indices()

    state.positions = np.array([[0.0, 0.0], [10.0, 0.0], [0.0, 10.0]])

    # Right triangle (0,0)-(10,0)-(0,10): shoelace area = 50 mm^2.
    # NOTE: EMIMetrics.*_loop_area_mm2 fields store the estimated loop
    # *inductance* (nH), not the raw area — the area-named fields were
    # repurposed (see measure_emi). Verify measure_emi feeds the correct
    # area+perimeter into the inductance estimator.
    metrics = measure_emi(state, netlist, loop_refs=[["U1", "U2", "U3"]])

    perimeter = 10.0 + 10.0 + np.sqrt(200.0)
    expected_inductance = estimate_loop_inductance(
        loop_area_mm2=50.0, perimeter_mm=perimeter
    )
    assert metrics.gate_loop_area_mm2 == pytest.approx(expected_inductance)

def test_measure_thermal(sample_setup):
    board, netlist, state = sample_setup
    # U1 at (25, 25), 25mm from all edges
    power = {"U1": 10.0} # 10W
    metrics = measure_thermal(state, netlist, board, power_dissipation=power)

    assert metrics.max_junction_temp_c > 40.0
    assert metrics.edge_distance_avg_mm == 25.0

def test_measure_routability(sample_setup):
    board, netlist, state = sample_setup
    metrics = measure_routability(state, netlist, board)

    assert metrics.total_wirelength_mm > 0
    assert metrics.max_congestion >= 0

def test_hv_lv_clearance(sample_setup):
    board, netlist, state = sample_setup
    # U1 is MCU_ZONE (LV), U2 is generic (LV)
    # Set U1 to HighVoltage class
    netlist.components[0].net_class = "HighVoltage"

    # U1 at (25, 25), U2 at (25, 30)
    # Sizes are 10x10.
    # U1: y=[20, 30], U2: y=[25, 35]
    # They overlap! Clearance should be 0.
    metrics = measure_geometric(state, netlist, board)
    assert metrics.min_hv_lv_clearance_mm == 0.0

    # Move U2 further away
    state.positions[1] = [25.0, 50.0]
    # U1: y=[20, 30], U2: y=[45, 55]
    # Gap = 45 - 30 = 15.0
    metrics = measure_geometric(state, netlist, board)
    assert metrics.min_hv_lv_clearance_mm == 15.0
