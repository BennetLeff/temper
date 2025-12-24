
import jax.numpy as jnp

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Netlist
from temper_placer.losses.base import LossContext
from temper_placer.losses.boundary import BoundaryLoss


def test_boundary_loss_with_non_zero_origin():
    """
    Test that BoundaryLoss correctly handles boards with non-zero origins.
    Issue temper-uu4s: Optimizer places components outside board bounds
    when input PCB has non-zero origin.
    """
    # Create a board at (100, 100) with size 50x50
    board = Board(width=50.0, height=50.0, origin=(100.0, 100.0))

    # Create a netlist with one component
    comp = Component(ref="U1", footprint="test", bounds=(10.0, 10.0))
    netlist = Netlist(components=[comp])

    # Context
    bounds = jnp.array([[10.0, 10.0]])
    fixed_mask = jnp.array([False])
    context = LossContext(board=board, netlist=netlist, bounds=bounds, fixed_mask=fixed_mask)

    # Boundary Loss
    loss_fn = BoundaryLoss(edge_margin=0.0)

    # Case 1: Component at board-relative (25, 25) -> absolute (125, 125)
    # This should have ZERO loss because it's in the middle of the board
    pos_absolute = jnp.array([[125.0, 125.0]])
    rot = jnp.array([[1.0, 0.0, 0.0, 0.0]]) # 0 degrees

    result = loss_fn(pos_absolute, rot, context)
    print(f"Loss at absolute (125, 125): {result.value}")

    # Case 2: Component at absolute (25, 25)
    # This should have high loss because it's far from board starting at (100, 100)
    pos_outside = jnp.array([[25.0, 25.0]])
    result_outside = loss_fn(pos_outside, rot, context)
    print(f"Loss at absolute (25, 25): {result_outside.value}")

    assert result.value == 0.0, f"Expected 0 loss for absolute position (125,125), got {result.value}"
    assert result_outside.value > 0.0, f"Expected positive loss for absolute position (25,25), got {result_outside.value}"

def test_boundary_loss_with_medium_board_fixture():
    """
    Test with the actual fixture mentioned in the issue.
    """
    from pathlib import Path

    from temper_placer.io.kicad_parser import parse_kicad_pcb

    fixture_path = Path("packages/temper-placer/tests/fixtures/medium_board.kicad_pcb")
    if not fixture_path.exists():
        print(f"Skipping fixture test, file not found: {fixture_path}")
        return

    result = parse_kicad_pcb(fixture_path)
    board = result.board
    netlist = result.netlist

    print(f"Loaded board: {board.width}x{board.height} at origin {board.origin}")

    # Context
    context = LossContext.from_netlist_and_board(netlist, board)

    # Boundary Loss
    loss_fn = BoundaryLoss(edge_margin=0.0)

    # Test a position that should be INSIDE the board (absolute center)
    # e.g., center of the board
    ox, oy = board.origin
    pos_absolute = jnp.array([[ox + board.width / 2, oy + board.height / 2]] * netlist.n_components)
    rot = jnp.zeros((netlist.n_components, 4)).at[:, 0].set(1.0)

    res = loss_fn(pos_absolute, rot, context)
    print(f"Loss at absolute center: {res.value}")

    assert res.value == 0.0, f"Expected 0 loss at absolute center, got {res.value}"

if __name__ == "__main__":
    test_boundary_loss_with_non_zero_origin()
    test_boundary_loss_with_medium_board_fixture()
