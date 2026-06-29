import numpy as np

from temper_placer.core.board import Board, Zone
from temper_placer.core.netlist import Component, Netlist
from temper_placer.optimizer.legalization import legalize_with_backtracking


def test_legalize_with_backtracking_basic():
    board = Board(width=110, height=100)
    # Two 50x100 components that overlap
    c1 = Component("U1", "Pkg", (50, 100))
    c2 = Component("U2", "Pkg", (50, 100))
    netlist = Netlist([c1, c2], [])

    # Overlapping positions
    positions = np.array([[25.0, 50.0], [30.0, 50.0]])

    legalized = legalize_with_backtracking(positions, netlist, board)

    # Should be separated: e.g. (25, 50) and (75.5, 50)
    assert abs(legalized[0, 0] - legalized[1, 0]) >= 50.0

def test_legalize_with_backtracking_zones():
    # Zone Z1 only allows U1
    board = Board(width=100, height=100, zones=[Zone("Z1", (0, 0, 50, 100))])

    c1 = Component("U1", "Pkg", (40, 40), zone="Z1")
    c2 = Component("U2", "Pkg", (40, 40)) # No zone, but should avoid U1
    netlist = Netlist([c1, c2], [])

    # U1 starts outside its zone
    positions = np.array([[75.0, 50.0], [75.0, 50.0]])

    legalized = legalize_with_backtracking(positions, netlist, board)

    # U1 should be in [0, 50]
    assert 0 <= legalized[0, 0] <= 50
    # U2 should be in [50, 100] to avoid U1
    assert 50 <= legalized[1, 0] <= 100
