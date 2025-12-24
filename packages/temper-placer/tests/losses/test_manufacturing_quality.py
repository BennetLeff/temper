
import jax.numpy as jnp
import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Netlist
from temper_placer.losses.aesthetic import RotationConsistencyLoss
from temper_placer.losses.base import LossContext
from temper_placer.losses.manufacturing_margin import (
    ManufacturingMarginConfig,
    ManufacturingMarginLoss,
)


@pytest.fixture
def mock_context_with_fiducials():
    # 3 components: U1, R1, FID1
    components = [
        Component("U1", "Package", (10.0, 10.0), [], (0.0, 0.0)),
        Component("R1", "Resistor", (5.0, 5.0), [], (0.0, 0.0)),
        Component("FID1", "Fiducial", (1.0, 1.0), [], (0.0, 0.0)),
    ]
    netlist = Netlist(components, [])
    board = Board(100.0, 100.0)
    return LossContext.from_netlist_and_board(netlist, board)

@pytest.fixture
def mock_context_with_types():
    # R1, R2 (Resistors), C1, C2 (Caps)
    components = [
        Component("R1", "R", (5,5), [], (0.0,0.0)),
        Component("R2", "R", (6,6), [], (0.0,0.0)),
        Component("C1", "C", (7,7), [], (0.0,0.0)),
        Component("C2", "C", (8,8), [], (0.0,0.0)),
    ]
    netlist = Netlist(components, [])
    board = Board(100.0, 100.0)
    return LossContext.from_netlist_and_board(netlist, board)

def test_manufacturing_margin_fiducial(mock_context_with_fiducials):
    # Setup positions: U1 and R1 are 0.5mm apart (safe for normal margin 0.1mm)
    # R1 and FID1 are 0.5mm apart (UNSAFE for fiducial margin 1.0mm)

    positions = jnp.array([
        [10.0, 10.0], # U1
        [10.5, 10.0], # R1 (0.5mm from U1)
        [11.0, 10.0], # FID1 (0.5mm from R1)
    ])

    # Dummy rotations (identity)
    rotations = jnp.tile(jnp.array([1., 0., 0., 0.]), (3, 1))

    # 1. Test with standard loss (no fiducial awareness or default config)
    config = ManufacturingMarginConfig(target_margin_mm=0.1, min_margin_mm=0.05, fiducial_margin_mm=1.0)
    loss_fn = ManufacturingMarginLoss(config=config, min_clearance_mm=0.2)

    # We expect high penalty because R1-FID1 dist is 0.5mm (centers) - widths...
    # Wait, component widths are needed.
    # In mock_context, we didn't set bounds in Component constructor clearly?
    # Component constructor: ref, footprint, bounds, ...
    # Let's check Component definition or assume default if simple.
    # Actually LossContext uses netlist.get_bounds_array().
    # In fixture we passed (10,10), (5,5), (1,1) as bounds.

    # U1: 10x10, R1: 5x5, FID1: 1x1
    # Half-dims: U1(5), R1(2.5), FID1(0.5)

    # Dist U1-R1:
    # Center diff x: 0.5.
    # Half width sum: 5 + 2.5 = 7.5.
    # Separation: 0.5 - 7.5 = -7.0 (Overlapping!)

    # Let's adjust positions to be non-overlapping but close.
    # U1 at 0, R1 at 10 (gap 10 - 5 - 2.5 = 2.5 > 0.1 ok)
    # FID1 at 20 (gap 20 - 10 - 2.5 - 0.5 = 10 - 3 = 7 > 1.0 ok)

    # Case 1: Gap = 0.5mm
    # U1 (w=10) at 0. R1 (w=5) at (5 + 2.5 + 0.5) = 8.0
    # Gap = 8.0 - 0 - 5 - 2.5 = 0.5.
    # 0.5 > 0.2 (min_clearance) + 0.1 (target) = 0.3. OK.

    # Case 2: Gap = 0.5mm to FID
    # FID1 (w=1) at (8.0 + 2.5 + 0.5 + 0.5) = 11.5
    # Gap = 11.5 - 8.0 - 2.5 - 0.5 = 0.5.
    # 0.5 < 1.0 (fiducial margin). FAIL.

    positions = jnp.array([
        [0.0, 0.0],  # U1
        [8.0, 0.0],  # R1 (Gap 0.5 to U1)
        [11.5, 0.0], # FID1 (Gap 0.5 to R1)
    ])

    result = loss_fn(positions, rotations, mock_context_with_fiducials)

    # We expect penalties.
    # U1-R1 margin: 0.5 - 0.2 = 0.3 > 0.1 (target). Penalty ~0.
    # R1-FID margin: 0.5 - 1.0 = -0.5 (violation!). High penalty.
    # U1-FID margin: huge gap. 0 penalty.

    assert result.value > 100.0, "Should have high penalty for fiducial violation"

def test_rotation_consistency_types(mock_context_with_types):
    # R1, C1 at 0 deg. R2, C2 at 90 deg.
    # Global entropy is high (50% 0, 50% 90).
    # Type entropy:
    # R group: 0 and 90 -> high entropy.
    # C group: 0 and 90 -> high entropy.

    positions = jnp.zeros((4, 2))

    # Case A: Mixed (bad)
    rotations_mixed = jnp.array([
        [1., 0., 0., 0.], # R1 0
        [0., 1., 0., 0.], # R2 90
        [1., 0., 0., 0.], # C1 0
        [0., 1., 0., 0.], # C2 90
    ])

    loss_fn = RotationConsistencyLoss()
    res_mixed = loss_fn(positions, rotations_mixed, mock_context_with_types)

    # Case B: Consistent per type (good)
    # R: all 0. C: all 90.
    # Global entropy still high (mixed 0 and 90).
    # But Per-Type entropy should be 0.

    rotations_type_consistent = jnp.array([
        [1., 0., 0., 0.], # R1 0
        [1., 0., 0., 0.], # R2 0
        [0., 1., 0., 0.], # C1 90
        [0., 1., 0., 0.], # C2 90
    ])

    res_consistent = loss_fn(positions, rotations_type_consistent, mock_context_with_types)

    print(f"Mixed: {res_mixed.value}, Consistent: {res_consistent.value}")
    assert res_consistent.value < res_mixed.value, "Type-consistent layout should have lower loss"
    assert res_consistent.value < 0.1, "Type-consistent layout should have near-zero loss"

if __name__ == "__main__":
    pass
