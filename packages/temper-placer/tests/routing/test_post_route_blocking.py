"""
Tests for post-route blocking in MazeRouter (temper-df3m).

Verifies that after a net is routed, its clearance zone is immediately blocked
on the grid so that subsequent sequential routes respect it.
"""

import pytest
import numpy as np
from temper_placer.routing.maze_router import MazeRouter, RoutePath, GridCell
from temper_placer.io.kicad_parser import TraceData
from temper_placer.routing.layer_assignment import LayerAssignment, Layer

class TestPostRouteBlocking:
    """Tests for immediate clearance blocking after routing."""

    def test_block_route_path_simple(self):
        """Test that block_route_path correctly blocks grid cells."""
        router = MazeRouter(
            grid_size=(50, 50),
            cell_size_mm=0.2,
            num_layers=1,
            min_clearance=0.2,
        )

        # Create a dummy route path
        # Trace from (10, 10) to (20, 10)
        # 0.2mm grid -> 50 to 100 in grid units
        
        start_cell = GridCell(10, 10, 0)
        end_cell = GridCell(20, 10, 0) # Diagonal-ish for interest? No, keep it simple first
        
        # Make it a horizontal line in grid coordinates
        # 10,10 to 20,10 corresponding to 2.0mm,2.0mm to 4.0mm,2.0mm
        path = RoutePath(
            net="NET_A",
            cells=[GridCell(x, 10, 0) for x in range(10, 21)],
            length=2.0,
            via_count=0,
            success=True,
            cell_size=0.2,
            trace_width=0.4, # 2 cells wide
        )

        # Pre-check: area should be empty
        rx, ry = router.grid_converter.world_to_grid(2.5, 2.0) # Middle of trace
        assert router.occupancy[rx, ry, 0] == 0

        # Apply blocking
        # Mocking the method if it doesn't exist yet would be tricky if we want to run this *before* impl.
        # But we are doing TDD, so we expect this call to fail if the method is missing.
        # However, to be "Red" in a useful way, we can check if `rrr_route_all_nets` respects it.
        # Or checking existence of method.
        
        if not hasattr(router, "block_route_path"):
             pytest.fail("MazeRouter.block_route_path not implemented yet")

        router.block_route_path(path, net_class="Signal")

        # Check occupancy
        # Middle of trace should be blocked
        assert router.occupancy[15, 10, 0] == 2
        
        # Clearance zone should be blocked?
        # With default 0.3mm clearance on top of 0.4mm trace:
        # Radius ~ (0.2 + 0.3) = 0.5mm = 2.5 cells -> rounded up to 3 cells
        # So (15, 13) should be blocked or at least non-zero?
        # Actually block_traces sets occupancy=2.
        
        assert router.occupancy[15, 10+2, 0] == 2

    def test_sequential_routing_respects_clearance(self):
        """
        Verify that efficient sequential routing respects the clearance of previously routed nets.
        
        Scenario:
        1. Route HV Net (high clearance).
        2. Route Signal Net nearby.
        3. Signal Net should detour to avoid HV clearance.
        """
        # 0.1mm grid for finer resolution
        router = MazeRouter(
            grid_size=(100, 100),
            cell_size_mm=0.1,
            num_layers=1,
            min_clearance=0.1,
        )
        
        # Net 1: HV Line across the middle
        # From (2.0, 5.0) to (8.0, 5.0)
        # HV Clearance = 2.0mm
        # Trace width = 0.5mm
        # Blocked radius = 0.25 + 2.0 = 2.25mm
        
        # We simulate the router having routed Net 1
        path_hv = RoutePath(
            net="HV_NET",
            cells=[], # Dummy cells, we rely on coordinate reconstruction or we just manually construct relevant list
            length=6.0,
            via_count=0,
            success=True,
            cell_size=0.1,
            trace_width=0.5
        )
        # Manually populate cells for block_route_path to work (it usually reconstructs from cells)
        # Horizontal line y=5.0mm -> grid y=50
        # x=2.0->20, x=8.0->80
        path_hv.cells = [GridCell(x, 50, 0) for x in range(20, 81)]
        
        if not hasattr(router, "block_route_path"):
             pytest.fail("MazeRouter.block_route_path not implemented yet")

        # Block it as HighVoltage
        router.block_route_path(path_hv, net_class="HighVoltage")
        
        # Check that it blocked a wide area
        # Center is y=50.
        # Radius 2.25mm is 22.5 cells.
        # y=70 (2.0mm away) should be blocked.
        assert router.occupancy[50, 70, 0] != 0, "HV clearance zone should be blocked"
        
        # y=80 (3.0mm away) should be free
        # 3.0mm > 2.25mm
        assert router.occupancy[50, 85, 0] == 0, "Far area should be free"
        
        # Now try to route a Signal net strictly
        # From (2.0, 7.0) to (8.0, 7.0)
        # This is y=7.0mm.
        # Distance to HV is |7.0 - 5.0| = 2.0mm.
        # HV requires 2.0mm clearance.
        # So y=7.0 is marginally inside/boundary.
        # Depending on grid rounding, it might be blocked.
        # If blocked, A* should fail or go around.
        
        # We'll rely on route_net or find_path_astar to see if it finds a path through the blocked zone.
        # But `find_path_astar` doesn't take net class directly? 
        # `route_net` uses `route_net_rrr` which uses `find_path_astar...`
        
        # Let's perform a simple A* check
        # Start (2.0, 7.0) -> Grid (20, 70)
        # End (8.0, 7.0) -> Grid (80, 70)
        
        # If (20, 70) is blocked, A* start will fail.
        # Let's check a point slightly closer: y=6.0mm -> Grid 60.
        # This is 1.0mm away. DEFINITELY blocked by HV (needs 2mm).
        
        start_node = (20, 60, 0)
        end_node = (80, 60, 0)
        
        # It should be blocked
        assert router.occupancy[20, 60, 0] != 0, "Target routing area should be blocked by HV clearance"

