import math

from temper_placer.core.board import Board, MountingHole
from temper_placer.routing.layer_assignment import Layer, LayerAssignment
from temper_placer.routing.maze_router import MazeRouter


def test_exp20_mounting_hole_avoidance():
    """EXP-20: Verify that routing avoids mounting holes."""
    # 1. Setup Board with Mounting Hole at (50, 50) with 5mm keepout radius
    board = Board(
        width=100.0,
        height=100.0,
        origin=(0.0, 0.0),
        mounting_holes=[
            MountingHole(position=(50.0, 50.0), diameter=3.0, keepout_radius=5.0)
        ]
    )

    # 2. Setup Router
    router = MazeRouter.from_board(board, cell_size_mm=1.0)

    # 3. Block features
    router.block_board_features(board)

    # Verify the hole is blocked
    # (50, 50) should be blocked
    assert router.occupancy[50, 50, 0] == -1

    # 4. Define Net
    # Pins at (30, 50) and (70, 50). Direct path goes through (50, 50).
    # Pins are 20mm from center. Hole radius 5mm. Unblock radius 5mm.
    # Safe from accidental unblocking.
    net_name = "TEST_NET"
    pin_positions = [(30.0, 50.0), (70.0, 50.0)]

    # 5. Route
    # Use L1_TOP only to force 2D avoidance
    assignment = LayerAssignment(net=net_name, primary_layer=Layer.L1_TOP, allowed_layers={Layer.L1_TOP})

    path = router.route_net_rrr(
        net_name=net_name,
        pin_positions=pin_positions,
        assignment=assignment
    )

    # 6. Verify Success
    assert path.success, "Routing failed to find a path around the mounting hole"

    # 7. Verify Detour
    # Direct distance is 40mm.
    # Detour around 5mm radius hole (diameter 10).
    # Path should be > 40.
    # Should be at least 40 + (circumference/2 - diameter) ?
    # Or just check it's not 40 (straight line).
    print(f"Path length: {path.length}")
    assert path.length > 42.0, "Path went through the mounting hole (too short)"

    # 8. Verify Geometry
    # Ensure no cell in the path is within the keepout radius
    # Keepout is circle at (50, 50) radius 5.0
    violations = 0
    for cell in path.cells:
        wx = cell.x * 1.0
        wy = cell.y * 1.0
        dist_sq = (wx - 50.0)**2 + (wy - 50.0)**2

        # We allow grazing the edge, but technically blocked cells are center-based.
        # If cell center is within radius, it was blocked.
        # So we shouldn't see any cell with dist <= 5.0
        if dist_sq <= 25.0:
            violations += 1
            print(f"Violation at ({wx}, {wy}), dist={math.sqrt(dist_sq)}")

    assert violations == 0, f"Path intersects mounting hole at {violations} points"
