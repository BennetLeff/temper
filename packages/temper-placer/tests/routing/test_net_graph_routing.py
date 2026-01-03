
import pytest
from temper_placer.core.board import Board
from temper_placer.core.net_graph import NetGraph, SubNetEdge
from temper_placer.routing.maze_router import MazeRouter, RoutePath

class TestNetGraphRouting:
    def test_route_net_with_graph(self):
        # 20x20mm board
        board = Board(width=20.0, height=20.0)
        
        # Define pins (using dict instead of Netlist for simplicity as route_net_with_graph takes dict)
        pin_positions = {
            "R_SENSE.1": (10.0, 10.0), # Center
            "LOAD.1": (5.0, 10.0),     # Left
            "MCU.ADC1": (10.0, 15.0),  # Top
        }
        
        # Define Graph
        graph = NetGraph(net_name="TEST_NET")
        
        # Edge 1: High Current (2.0mm)
        edge1 = SubNetEdge(
            source_pin="R_SENSE.1",
            sink_pin="LOAD.1",
            trace_width_mm=2.0,
            priority=1
        )
        graph.edges.append(edge1)
        
        # Edge 2: Signal (0.2mm)
        edge2 = SubNetEdge(
            source_pin="R_SENSE.1",
            sink_pin="MCU.ADC1",
            trace_width_mm=0.2,
            priority=0
        )
        graph.edges.append(edge2)
        
        # Router
        # Use fine grid to allow precise widths
        router = MazeRouter.from_board(board, cell_size_mm=0.1)
        
        # Route
        path = router.route_net_with_graph(
            net_name="TEST_NET",
            pin_positions=pin_positions,
            graph=graph,
            assignment=None
        )
        
        assert path.success
        assert len(path.segments) == 2
        
        # Verify segments
        # Segment 0 (Priority 1) should be Edge 1 (Width 2.0)
        seg0 = path.segments[0]
        assert seg0.trace_width == 2.0
        # Check if it goes to LOAD.1 (5, 10)
        # We can check length or endpoints roughly
        
        # Segment 1 (Priority 0) should be Edge 2 (Width 0.2)
        seg1 = path.segments[1]
        assert seg1.trace_width == 0.2
        
        # Verify connectivity
        # Both segments should share the start point (R_SENSE.1 at 10,10)
        # We can check cells.
        
        print(f"Segment 0 length: {seg0.length}")
        print(f"Segment 1 length: {seg1.length}")

    def test_star_node_tap_prevention(self):
        # 20x20mm board
        board = Board(width=20.0, height=20.0)
        
        # Pins in a L shape
        # Center (Star), Right, Top
        # We want to route Star -> Right and then Star -> Top.
        # If it taps, it might go Star -> (halfway to Right) -> Top.
        pin_positions = {
            "STAR.1": (10.0, 10.0), # Center
            "RIGHT.1": (15.0, 10.0), 
            "TOP.1": (10.0, 15.0),
        }
        
        # Case 1: No star nodes (tapping allowed/encouraged by distance)
        graph_no_star = NetGraph(net_name="GND")
        graph_no_star.edges.append(SubNetEdge("STAR.1", "RIGHT.1", priority=1))
        graph_no_star.edges.append(SubNetEdge("STAR.1", "TOP.1", priority=0))
        
        # Case 2: With star nodes (tapping forbidden)
        graph_star = NetGraph(net_name="GND_STAR")
        graph_star.star_nodes.add("STAR.1")
        graph_star.edges.append(SubNetEdge("STAR.1", "RIGHT.1", priority=1))
        graph_star.edges.append(SubNetEdge("STAR.1", "TOP.1", priority=0))
        
        router = MazeRouter.from_board(board, cell_size_mm=0.5)
        
        # Route with star constraints
        path_star = router.route_net_with_graph(
            net_name="GND_STAR",
            pin_positions=pin_positions,
            graph=graph_star,
            assignment=None
        )
        
        assert path_star.success
        assert len(path_star.segments) == 2
        
        # For Star case, the segments should be orthogonal (mostly)
        # and NOT share any cells except near STAR.1.
        seg0_cells = set((c.x, c.y, c.layer) for c in path_star.segments[0].cells)
        seg1_cells = set((c.x, c.y, c.layer) for c in path_star.segments[1].cells)
        
        # Common cells should only be near the star point (rad 2 unmasking)
        common = seg0_cells.intersection(seg1_cells)
        
        # Star point grid coords
        gx, gy = router._world_to_grid(10.0, 10.0)
        
        for cx, cy, cl in common:
            # All common cells must be within distance 3 of star point
            dist = abs(cx - gx) + abs(cy - gy)
            assert dist <= 3, f"Found common cell ({cx}, {cy}) too far from star point! dist={dist}"
        
        print(f"Star Point common cells: {len(common)}")
