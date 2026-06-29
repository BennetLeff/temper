"""
Unit tests for LayerAssignmentStage.

Tests net-to-layer assignment based on net class rules.
"""

import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.deterministic import BoardState
from temper_placer.deterministic.stages import LayerAssignmentStage


def test_layer_assignment_by_net_class():
    """Test that nets are assigned to correct layers based on net class."""
    board = Board(width=100, height=100)

    # Create components
    c1 = Component(ref="Q1", footprint="TO-247", bounds=(5, 5),
                   pins=[Pin("1", "C", (0, 0), net="AC_L")],
                   initial_position=(10, 10))
    c2 = Component(ref="C1", footprint="CAP", bounds=(3, 3),
                   pins=[Pin("1", "1", (0, 0), net="GND")],
                   initial_position=(20, 20))
    c3 = Component(ref="U1", footprint="IC", bounds=(4, 4),
                   pins=[Pin("1", "VDD", (0, 0), net="+3V3")],
                   initial_position=(30, 30))
    c4 = Component(ref="R1", footprint="0603", bounds=(1.6, 0.8),
                   pins=[Pin("1", "1", (0, 0), net="SPI_CLK")],
                   initial_position=(40, 40))

    # Create nets with net classes
    nets = [
        Net("AC_L", [("Q1", "C")], net_class="HighVoltage"),
        Net("GND", [("C1", "1")], net_class="Ground"),
        Net("+3V3", [("U1", "VDD")], net_class="Power"),
        Net("SPI_CLK", [("R1", "1")], net_class="Signal"),
    ]

    netlist = Netlist(components=[c1, c2, c3, c4], nets=nets)
    initial_state = BoardState(board=board, netlist=netlist)

    # Run layer assignment
    stage = LayerAssignmentStage()
    result_state = stage.run(initial_state)

    # Convert assignments to dict for easy checking
    assignments = {la.net_name: la.layer for la in result_state.layer_assignments}

    # Verify layer assignments
    assert assignments["AC_L"] == 0  # HighVoltage -> L0 (Top)
    assert assignments["GND"] == 1   # Ground -> L1 (Inner GND)
    assert assignments["+3V3"] == 2  # Power -> L2 (Inner Power)
    assert assignments["SPI_CLK"] == 0  # Signal -> L0 (Top)


def test_manual_layer_assignment():
    """Test that manual assignments override net class rules."""
    board = Board(width=100, height=100)

    c1 = Component(ref="R1", footprint="0603", bounds=(1.6, 0.8),
                   pins=[Pin("1", "1", (0, 0), net="TEST_NET")],
                   initial_position=(10, 10))

    nets = [Net("TEST_NET", [("R1", "1")], net_class="Signal")]
    netlist = Netlist(components=[c1], nets=nets)
    initial_state = BoardState(board=board, netlist=netlist)

    # Manually assign to layer 3 (override default layer 0 for Signal)
    stage = LayerAssignmentStage(layer_assignments={"TEST_NET": 3})
    result_state = stage.run(initial_state)

    assignments = {la.net_name: la.layer for la in result_state.layer_assignments}
    assert assignments["TEST_NET"] == 3  # Manual override


def test_all_nets_assigned():
    """Test that all nets get assigned to some layer."""
    board = Board(width=100, height=100)

    # Create multiple nets with different classes
    components = []
    nets = []
    for i in range(10):
        comp = Component(ref=f"R{i}", footprint="0603", bounds=(1.6, 0.8),
                        pins=[Pin("1", "1", (0, 0), net=f"NET_{i}")],
                        initial_position=(10 + i*5, 10))
        components.append(comp)
        nets.append(Net(f"NET_{i}", [(f"R{i}", "1")], net_class="Signal"))

    netlist = Netlist(components=components, nets=nets)
    initial_state = BoardState(board=board, netlist=netlist)

    stage = LayerAssignmentStage()
    result_state = stage.run(initial_state)

    # All nets should have assignments
    assert len(result_state.layer_assignments) == 10

    # All should be assigned to layer 0 (Signal class default)
    for la in result_state.layer_assignments:
        assert la.layer == 0
        assert la.allow_layer_change == True


def test_layer_assignment_empty_netlist():
    """Test handling of empty netlist."""
    board = Board(width=100, height=100)
    netlist = Netlist(components=[], nets=[])
    initial_state = BoardState(board=board, netlist=netlist)

    stage = LayerAssignmentStage()
    result_state = stage.run(initial_state)

    # Should handle gracefully with no assignments
    assert len(result_state.layer_assignments) == 0


def test_differential_pair_layer_assignment():
    """Test that differential pair nets are assigned to same layer."""
    board = Board(width=100, height=100)

    c1 = Component(ref="J1", footprint="USB", bounds=(5, 5),
                   pins=[
                       Pin("1", "D+", (0, 0), net="USB_D+"),
                       Pin("2", "D-", (1, 0), net="USB_D-")
                   ],
                   initial_position=(10, 10))

    nets = [
        Net("USB_D+", [("J1", "D+")], net_class="Differential"),
        Net("USB_D-", [("J1", "D-")], net_class="Differential"),
    ]

    netlist = Netlist(components=[c1], nets=nets)
    initial_state = BoardState(board=board, netlist=netlist)

    stage = LayerAssignmentStage()
    result_state = stage.run(initial_state)

    assignments = {la.net_name: la.layer for la in result_state.layer_assignments}

    # Both differential nets should be on same layer (L0 for controlled impedance)
    assert assignments["USB_D+"] == 0
    assert assignments["USB_D-"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
