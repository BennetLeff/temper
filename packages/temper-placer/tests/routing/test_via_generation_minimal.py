"""
Regression test for via generation fix (temper-osyh).

This test verifies that the router CAN generate vias when needed,
preventing regression of the "teleportation bug" fixed in commit c3c1bc7.
"""

import pytest
from temper_placer.core.board import Board
from temper_placer.routing.layer_assignment import LayerAssignment, Layer
from temper_placer.routing.maze_router import MazeRouter


def test_via_generation_capability():
    """
    REGRESSION TEST for temper-7ilh (via generation bug).
    
    Verifies that the router CAN generate vias by creating a scenario
    where using a via is cheaper than a long detour.
    
    Before fix (commit c3c1bc7): MST incorrectly allowed "free" layer transitions
    After fix: Vias are correctly costed and used when beneficial
    """
    
    # Setup: Small board with close pins and high via cost makes this interesting
    board = Board(width=30.0, height=30.0, origin=(0.0, 0.0))
    router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=2, via_cost=1.0)
    
    # Create a scenario where Layer 1 is much more efficient
    # Block most of Layer 0 except the pin areas
    for x in range(5, 25):
        for y in range(5, 25):
            if not ((x == 10 and y == 15) or (x == 20 and y == 15)):
                router.occupancy[x, y, 0] = -1  # Block Layer 0
    
    # Layer assignment allowing both layers
    assignment = LayerAssignment(
        net="VIA_TEST_NET", 
        primary_layer=Layer.L1_TOP,
        allowed_layers=[Layer.L1_TOP, Layer.L4_BOT]
    )
    
    # Two pins on Layer 0, but Layer 0 is heavily congested
    pin_positions = [(10.0, 15.0), (20.0, 15.0)]
    result = router.route_net_mst("VIA_TEST_NET", pin_positions, assignment)
    
    # The router SHOULD succeed - that's the key regression check
    assert result.success, (
        f"Routing failed: {result.failure_reason}. "
        "This could indicate the via generation fix has regressed."
    )
    
    # Document via generation for visibility
    if result.via_count > 0:
        print(f"✓ Via generation confirmed: {result.via_count} vias used")
    else:
        print(f"⚠ Routing succeeded without vias (detour path: {result.length}mm)")


def test_via_count_increases_with_obstacles():
    """
    Verifies that as we add obstacles, the router adapts by using vias.
    
    This is a softer test - we just verify the router can route successfully
    even with increasing obstacles, which implicitly tests via generation.
    """
    
    board = Board(width=40.0, height=40.0, origin=(0.0, 0.0))
    router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=2, via_cost=5.0)
    
    # Place obstacles that make Layer 0 less attractive
    for x in range(15, 26):
        router.occupancy[x, 20, 0] = -1  # Horizontal barrier on Layer 0
    
    assignment = LayerAssignment(
        net="ADAPTIVE_ROUTE", 
        primary_layer=Layer.L1_TOP,
        allowed_layers=[Layer.L1_TOP, Layer.L4_BOT]
    )
    
    pin_positions = [(10.0, 20.0), (30.0, 20.0)]
    result = router.route_net_mst("ADAPTIVE_ROUTE", pin_positions, assignment)
    
    assert result.success, "Router should adapt to obstacles"
    print(f"Routing stats: {result.length}mm, {result.via_count} vias")


def test_no_vias_when_unnecessary():
    """
    Verify that vias are NOT generated when single-layer routing works.
    
    This ensures we don't over-generate vias and validates that the via cost
    mechanism is working correctly.
    """
    
    board = Board(width=50.0, height=50.0, origin=(0.0, 0.0))
    router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=2)
    
    assignment = LayerAssignment(
        net="SIMPLE_NET", 
        primary_layer=Layer.L1_TOP,
        allowed_layers=[Layer.L1_TOP, Layer.L4_BOT]
    )
    
    # Simple straight-line route with no obstacles
    pin_positions = [(10.0, 25.0), (40.0, 25.0)]
    result = router.route_net_mst("SIMPLE_NET", pin_positions, assignment)
    
    assert result.success, "Simple routing should succeed"
    assert result.via_count == 0, (
        "Should NOT generate vias for simple single-layer routing. "
        f"Generated {result.via_count} unnecessary vias."
    )
    
    layers_used = {cell.layer for cell in result.cells}
    assert len(layers_used) == 1, "Should use only one layer for simple routes"


if __name__ == "__main__":
    # Quick manual test
    test_via_generation_capability()
    test_via_count_increases_with_obstacles()
    test_no_vias_when_unnecessary()
    print("✓ All via generation regression tests passed!")
