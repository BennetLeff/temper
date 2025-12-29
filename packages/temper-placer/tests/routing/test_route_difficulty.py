"""
Tests for route difficulty gradient in MazeRouter.
"""

import jax.numpy as jnp
from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.routing.maze_router import MazeRouter
from temper_placer.routing.layer_assignment import Layer, LayerAssignment

def test_route_difficulty_gradient():
    """Verify that routing difficulty is recorded and reflects obstacles."""
    board = Board(width=50.0, height=50.0)
    router = MazeRouter.from_board(board, cell_size_mm=1.0)
    
    # Create two pins to route between
    pin1_pos = (5.0, 5.0)
    pin2_pos = (15.0, 5.0)
    
    # Assignment
    assignment = LayerAssignment(
        net="NET1",
        primary_layer=Layer.L1_TOP,
        allowed_layers={Layer.L1_TOP},
        vias_required=False,
        reason="Test",
    )
    
    # 1. Route on empty board
    res_empty = router.route_net("NET1", [pin1_pos, pin2_pos], assignment)
    assert res_empty.success
    # On empty board, density is 0, no neighbors blocked.
    # Base difficulty should be 0.
    assert res_empty.difficulty == 0.0
    
    # 2. Add an obstacle on both sides of the path
    # Path is at y=5. Block y=4 and y=6.
    router.block_rect(5, 4, 11, 1) # x=[5,15], y=4
    router.block_rect(5, 6, 11, 1) # x=[5,15], y=6
    
    # Reset occupancy for routed cells but keep blocked cells
    router.occupancy = jnp.where(router.occupancy == 2, 0, router.occupancy)
    
    res_obstacle = router.route_net("NET1", [pin1_pos, pin2_pos], assignment)
    assert res_obstacle.success
    # Should have higher difficulty because it must pass through y=5 which is flanked by blocked cells
    assert res_obstacle.difficulty > 0.0
    assert any(d > 0 for d in res_obstacle.cell_difficulties)
    
    # 3. Increase component density
    comp1 = Component(ref="U1", footprint="S", bounds=(5, 5))
    positions = jnp.array([[10.0, 10.0]])
    router.block_components([comp1], positions)
    
    # Reset occupancy for routed cells
    router.occupancy = jnp.where(router.occupancy == 2, 0, router.occupancy)
    
    res_dense = router.route_net("NET1", [pin1_pos, pin2_pos], assignment)
    assert res_dense.success
    # Density at (10, 5) from U1 at (10, 10) should be non-zero
    assert res_dense.difficulty > res_obstacle.difficulty
