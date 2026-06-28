import pytest
import numpy as np
from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist, Component
from temper_placer.router_v6._routing_shim.congestion import CongestionResult, CongestionGrid, Bottleneck
from temper_placer.placer.adjustment import adjust_for_congestion

def test_adjust_for_congestion():
    board = Board(width=100, height=100)
    c1 = Component("U1", "Pkg", (10, 10))
    netlist = Netlist([c1], [])
    
    positions = np.array([[50.0, 50.0]])
    
    # Mock congestion at (50, 50)
    grid = CongestionGrid.from_board(board)
    bottleneck = Bottleneck(x=50, y=50, utilization=2.0, overflow=1.0)
    congestion = CongestionResult(grid=grid, bottlenecks=[bottleneck])
    
    adjusted = adjust_for_congestion(positions, netlist, board, congestion)
    
    # U1 should have been pushed away from (50, 50)
    # The bottleneck coordinate for x=50 cell is 50.5mm
    assert not np.allclose(adjusted[0], [50.0, 50.0])
