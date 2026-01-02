
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
