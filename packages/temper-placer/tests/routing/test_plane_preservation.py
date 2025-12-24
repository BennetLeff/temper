from temper_placer.core.board import Board, Layer, LayerStackup
from temper_placer.routing.maze_router import GridCell, MazeRouter


def test_traces_blocked_on_plane_layer():
    """Traces (horizontal/vertical moves) should be blocked on plane layers."""
    # Define a stackup where L1 is signal and L2 is plane
    stackup = LayerStackup(layers=[
        Layer("F.Cu", "signal", is_routable=True),
        Layer("GND", "plane", is_routable=False)
    ])

    router = MazeRouter(
        grid_size=(10, 10),
        cell_size_mm=1.0,
        num_layers=2,
        layer_stackup=stackup
    )

    # Try to find a path on Layer 1 (Plane)
    # Start (0, 5, 1), End (9, 5, 1)
    # This should fail because x/y moves are blocked on layer 1
    path = router.find_path(start=(0, 5), end=(9, 5), layer=1, allow_layer_change=False)

    assert path is None, "Horizontal/vertical routing should be blocked on plane layers"

def test_vias_pierce_plane_layer():
    """Vias should still be able to pierce plane layers to reach signal layers."""
    # Define a 3-layer stackup: L1(signal), L2(plane), L3(signal)
    stackup = LayerStackup(layers=[
        Layer("L1", "signal", is_routable=True),
        Layer("L2", "plane", is_routable=False),
        Layer("L3", "signal", is_routable=True)
    ])

    router = MazeRouter(
        grid_size=(10, 10),
        cell_size_mm=1.0,
        num_layers=3,
        layer_stackup=stackup
    )

    # Force a path that MUST go to L3
    # Block L1 and L2 at the destination (5, 5)
    # MazeRouter.block_rect uses (x, y, width, height, layer)
    router.block_rect(5, 5, 1, 1, layer=0)
    router.block_rect(5, 5, 1, 1, layer=1)

    # Route from L1 (0, 0, 0) to (5, 5)
    path = router.find_path(
        start=(0, 0),
        end=(5, 5),
        layer=0,
        allow_layer_change=True,
        allowed_layers=[0, 1, 2]
    )

    assert path is not None, "Vias should be able to land on/pierce plane layers"
    # Verify it reached the final target on L3
    assert path[-1].x == 5 and path[-1].y == 5 and path[-1].layer == 2

    # Verify no horizontal moves on the plane layer if it was visited
    for i in range(len(path) - 1):
        c1, c2 = path[i], path[i+1]
        if c1.layer == 1:
            assert c1.x == c2.x and c1.y == c2.y, "Horizontal move detected on plane layer"

def test_signal_routing_around_plane():
    """Signal routing should succeed on signal layers even if planes exist."""
    stackup = LayerStackup.default_4layer() # L1(signal), L2(plane), L3(plane), L4(signal)

    router = MazeRouter(
        grid_size=(10, 10),
        cell_size_mm=1.0,
        num_layers=4,
        layer_stackup=stackup
    )

    # Route on L1
    path_l1 = router.find_path(start=(0, 0), end=(9, 9), layer=0)
    assert path_l1 is not None, "Signal routing on L1 should succeed"

    # Route on L4
    path_l4 = router.find_path(start=(0, 0), end=(9, 9), layer=3)
    assert path_l4 is not None, "Signal routing on L4 should succeed"

    # Route on L2 (Plane) - should fail
    path_l2 = router.find_path(start=(0, 0), end=(9, 9), layer=1)
    assert path_l2 is None, "Signal routing on L2 plane should fail"

def test_via_path_with_horizontal_segments():
    """Via path can have horizontal segments on signal layers but only vias on planes."""
    stackup = LayerStackup.default_4layer()

    router = MazeRouter(
        grid_size=(10, 10),
        cell_size_mm=1.0,
        num_layers=4,
        layer_stackup=stackup
    )

    # Start at (0,0) on L1, end at (9,9) on L4
    # Must use vias to get to L4. It can route horizontally on L1 or L4, but only vias on L2/L3.
    path = router.find_path(
        start=(0, 0),
        end=(9, 9),
        layer=0,
        allow_layer_change=True,
        allowed_layers=[0, 1, 2, 3]
    )

    assert path is not None
    # Verify no horizontal moves on plane layers (In1, In2)
    for i in range(len(path) - 1):
        c1, c2 = path[i], path[i+1]
        if c1.layer == 1 or c1.layer == 2:
            # If on a plane layer, next step MUST be a layer change
            assert c1.x == c2.x and c1.y == c2.y, f"Horizontal move detected on plane layer {c1.layer}"

def test_analyze_plane_integrity():
    """Should correctly identify plane integrity metrics from routing results."""
    from temper_placer.losses.plane_integrity import analyze_plane_integrity
    from temper_placer.routing.maze_router import RoutePath

    stackup = LayerStackup(layers=[
        Layer("L1", "signal", is_routable=True),
        Layer("L2", "plane", is_routable=False),
        Layer("L3", "signal", is_routable=True)
    ])
    board = Board(width=20.0, height=20.0, origin=(0, 0), zones=[], layer_stackup=stackup)

    # Mock 1: Path that only pierces the plane (OK)
    path1 = RoutePath(
        net="NET_OK",
        cells=[GridCell(0,0,0), GridCell(0,0,1), GridCell(0,0,2)],
        length=2.0,
        via_count=1,
        success=True
    )

    # Mock 2: Path that illegally routes horizontally on the plane (ERROR)
    path2 = RoutePath(
        net="NET_BAD",
        cells=[GridCell(1,1,1), GridCell(2,1,1), GridCell(3,1,1)],
        length=2.0,
        via_count=0,
        success=True
    )

    results = {"NET_OK": path1, "NET_BAD": path2}
    metrics = analyze_plane_integrity(results, board)

    assert len(metrics) == 1
    m = metrics[0]
    assert m.layer_name == "L2"
    assert m.via_count == 4 # (0,0,1) from NET_OK, plus (1,1,1), (2,1,1), (3,1,1) from NET_BAD
    assert m.horizontal_segment_count == 2 # (1,1,1)->(2,1,1) and (2,1,1)->(3,1,1)
    assert m.integrity_score < 1.0
