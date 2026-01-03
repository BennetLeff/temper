import pytest
import numpy as np
from temper_placer.routing.maze_router import MazeRouter
from temper_placer.core.board import Board


def test_occupancy_prevents_crossing_strict_mode():
    """Occupancy grid blocks crossing when soft_blocking=False."""
    
    # Setup: 10x10mm board with 2 nets crossing
    board = Board(width=10.0, height=10.0, origin=(0.0, 0.0))
    router = MazeRouter.from_board(
        board,
        cell_size_mm=1.0,
        num_layers=1,
        soft_blocking=False  # ← STRICT MODE
    )
    
    # Net 1: Block a horizontal line at y=5 to force Net 2 to cross it
    for x in range(10):
        router.occupancy[x, 5, 0] = 2  # 2 = occupied by another net
    
    # Attempt to route Net 2: from (5, 1) to (5, 9) - vertical (crosses the line at (5, 5))
    path2 = router.route_net_rrr(
        "Net2", 
        pin_positions=[(5.0, 1.0), (5.0, 9.0)], 
        assignment=None,
        p_scale=1.0
    )
    
    # Expected: Should FAIL because cell (5, 5) is occupied by Net 1 and soft_blocking=False
    assert not path2.success, "Router should fail when path blocked by occupied cell in strict mode"


def test_soft_blocking_allows_crossing():
    """Occupancy grid allows crossing (with penalty) when soft_blocking=True."""
    
    board = Board(width=10.0, height=10.0, origin=(0.0, 0.0))
    router = MazeRouter.from_board(
        board,
        cell_size_mm=1.0,
        num_layers=1,
        soft_blocking=True  # ← RRR MODE
    )
    
    # Block a horizontal line at y=5
    for x in range(10):
        router.occupancy[x, 5, 0] = 2
    
    # Net 2: Attempt to cross
    path2 = router.route_net_rrr(
        "Net2", 
        pin_positions=[(5.0, 1.0), (5.0, 9.0)], 
        assignment=None,
        p_scale=1.0
    )
    
    # Expected: Should SUCCEED (because soft_blocking allows violations)
    assert path2.success, "Soft blocking should allow crossing at high cost"
    
    # Verify that the path actually goes through (5, 5)
    cells = [(c.x, c.y, c.layer) for c in path2.cells]
    assert (5, 5, 0) in cells, "Path should include the occupied cell (5, 5)"
