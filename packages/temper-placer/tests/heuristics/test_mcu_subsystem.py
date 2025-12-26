import pytest
from pathlib import Path
import numpy as np
from temper_placer.core.board import Board, Zone
from temper_placer.core.netlist import Netlist, Component
from temper_placer.heuristics.mcu_subsystem import MCUSubsystemHeuristic

@pytest.fixture
def mock_env():
    board = Board(width=100, height=100, zones=[Zone("MCU_ZONE", (50, 50, 100, 100))])
    
    # Components from template
    components = [
        Component("U_MCU", "Pkg", (10, 10)),
        Component("Y1", "Pkg", (3, 3)),
        Component("C_XTAL1", "Pkg", (1, 1)),
        Component("C_XTAL2", "Pkg", (1, 1)),
        Component("C_MCU1", "Pkg", (1, 1)),
        Component("C_MCU2", "Pkg", (1, 1)),
        Component("C_MCU3", "Pkg", (1, 1)),
        Component("C_MCU4", "Pkg", (1, 1)),
        Component("J_DEBUG", "Pkg", (5, 5)),
        Component("SW_RESET", "Pkg", (5, 5)),
    ]
    netlist = Netlist(components, [])
    return board, netlist

def test_mcu_subsystem_heuristic(mock_env):
    board, netlist = mock_env
    heuristic = MCUSubsystemHeuristic()
    
    result = heuristic.apply(netlist, board)
    
    # MCU_ZONE center is (75, 75)
    # U_MCU is anchor, should be at (75, 75)
    idx_mcu = netlist.get_component_index("U_MCU")
    assert np.allclose(result.positions[idx_mcu], [75.0, 75.0])
    
    # Y1 should be at (75+8, 75+0) = (83, 75)
    idx_y1 = netlist.get_component_index("Y1")
    assert np.allclose(result.positions[idx_y1], [83.0, 75.0])
    
    # Check crystal caps are symmetric
    idx_c1 = netlist.get_component_index("C_XTAL1")
    idx_c2 = netlist.get_component_index("C_XTAL2")
    # Y1 is at (83, 75). C_XTAL1 is at (11, 2) rel to U_MCU -> (86, 77)
    # C_XTAL2 is at (11, -2) rel to U_MCU -> (86, 73)
    # They are symmetric around Y=75 (horizontal axis of crystal)
    assert result.positions[idx_c1][1] - 75.0 == pytest.approx(2.0)
    assert 75.0 - result.positions[idx_c2][1] == pytest.approx(2.0)
