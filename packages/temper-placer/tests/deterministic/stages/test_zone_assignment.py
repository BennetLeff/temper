"""
Unit tests for ZoneAssignmentStage.

Tests component-to-zone assignment based on net classes and component types.
"""

import pytest
from temper_placer.deterministic.stages.zone_assignment import ZoneAssignmentStage
from temper_placer.deterministic.state import BoardState
from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist, Component, Net, Pin


def test_hv_component_assigned_to_hv_zone():
    """Component on HighVoltage net should be assigned to HV zone."""
    # Setup
    c1 = Component(
        ref="Q1",
        footprint="TO-247",
        bounds=(5, 5),
        pins=[Pin("1", "C", (0, 0), net="AC_L")],
        initial_position=(10, 10)
    )
    nets = [Net("AC_L", [("Q1", "C")], net_class="HighVoltage")]
    netlist = Netlist(components=[c1], nets=nets)
    
    board = Board(width=100, height=100)
    initial_state = BoardState(board=board, netlist=netlist)
    
    # Execute
    stage = ZoneAssignmentStage()
    result_state = stage.run(initial_state)
    
    # Verify
    zone_map = {ref: zone for ref, zone in result_state.component_zone_map}
    assert "Q1" in zone_map
    assert zone_map["Q1"] == "HV"


def test_power_component_assigned_to_power_zone():
    """Bulk capacitor should be assigned to Power zone."""
    # Setup: Component on Power net class
    c1 = Component(
        ref="C1",
        footprint="CAP_1210",
        bounds=(3, 3),
        pins=[Pin("1", "1", (0, 0), net="VBUS")],
        initial_position=(30, 30)
    )
    nets = [Net("VBUS", [("C1", "1")], net_class="Power")]
    netlist = Netlist(components=[c1], nets=nets)
    
    board = Board(width=100, height=100)
    initial_state = BoardState(board=board, netlist=netlist)
    
    # Execute
    stage = ZoneAssignmentStage()
    result_state = stage.run(initial_state)
    
    # Verify
    zone_map = {ref: zone for ref, zone in result_state.component_zone_map}
    assert "C1" in zone_map
    assert zone_map["C1"] == "Power"


def test_mcu_component_assigned_to_mcu_zone():
    """Component with U_MCU prefix should be assigned to MCU zone."""
    # Setup
    c1 = Component(
        ref="U_MCU1",
        footprint="QFN56",
        bounds=(9, 9),
        pins=[Pin("1", "VDD", (0, 0), net="3V3")],
        initial_position=(90, 50)
    )
    nets = [Net("3V3", [("U_MCU1", "VDD")], net_class="Signal")]
    netlist = Netlist(components=[c1], nets=nets)
    
    board = Board(width=100, height=100)
    initial_state = BoardState(board=board, netlist=netlist)
    
    # Execute
    stage = ZoneAssignmentStage()
    result_state = stage.run(initial_state)
    
    # Verify
    zone_map = {ref: zone for ref, zone in result_state.component_zone_map}
    assert "U_MCU1" in zone_map
    assert zone_map["U_MCU1"] == "MCU"


def test_signal_component_default_zone():
    """Generic resistor should default to Signal zone."""
    # Setup
    c1 = Component(
        ref="R1",
        footprint="0603",
        bounds=(1.6, 0.8),
        pins=[Pin("1", "1", (0, 0), net="SENSE")],
        initial_position=(60, 60)
    )
    nets = [Net("SENSE", [("R1", "1")], net_class="Signal")]
    netlist = Netlist(components=[c1], nets=nets)
    
    board = Board(width=100, height=100)
    initial_state = BoardState(board=board, netlist=netlist)
    
    # Execute
    stage = ZoneAssignmentStage()
    result_state = stage.run(initial_state)
    
    # Verify
    zone_map = {ref: zone for ref, zone in result_state.component_zone_map}
    assert "R1" in zone_map
    assert zone_map["R1"] == "Signal"


def test_spi_component_assigned_to_mcu_zone():
    """Component on SPI net should be assigned to MCU zone."""
    # Setup
    c1 = Component(
        ref="U1",
        footprint="SOIC8",
        bounds=(5, 4),
        pins=[Pin("1", "MOSI", (0, 0), net="SPI_MOSI")],
        initial_position=(85, 50)
    )
    nets = [Net("SPI_MOSI", [("U1", "MOSI")], net_class="Signal")]
    netlist = Netlist(components=[c1], nets=nets)
    
    board = Board(width=100, height=100)
    initial_state = BoardState(board=board, netlist=netlist)
    
    # Execute
    stage = ZoneAssignmentStage()
    result_state = stage.run(initial_state)
    
    # Verify
    zone_map = {ref: zone for ref, zone in result_state.component_zone_map}
    assert "U1" in zone_map
    assert zone_map["U1"] == "MCU"


def test_multiple_components_different_zones():
    """Mix of components should be assigned to appropriate zones."""
    # Setup
    c_hv = Component(ref="Q1", footprint="TO-247", bounds=(5, 5),
                     pins=[Pin("1", "C", (0, 0), net="AC_L")], initial_position=(10, 10))
    c_power = Component(ref="C1", footprint="CAP_1210", bounds=(3, 3),
                        pins=[Pin("1", "1", (0, 0), net="VBUS")], initial_position=(40, 40))
    c_mcu = Component(ref="U_MCU1", footprint="QFN56", bounds=(9, 9),
                      pins=[Pin("1", "VDD", (0, 0), net="3V3")], initial_position=(90, 50))
    c_signal = Component(ref="R1", footprint="0603", bounds=(1.6, 0.8),
                         pins=[Pin("1", "1", (0, 0), net="SENSE")], initial_position=(65, 50))
    
    nets = [
        Net("AC_L", [("Q1", "C")], net_class="HighVoltage"),
        Net("VBUS", [("C1", "1")], net_class="Power"),
        Net("3V3", [("U_MCU1", "VDD")], net_class="Signal"),
        Net("SENSE", [("R1", "1")], net_class="Signal"),
    ]
    netlist = Netlist(components=[c_hv, c_power, c_mcu, c_signal], nets=nets)
    
    board = Board(width=100, height=100)
    initial_state = BoardState(board=board, netlist=netlist)
    
    # Execute
    stage = ZoneAssignmentStage()
    result_state = stage.run(initial_state)
    
    # Verify
    zone_map = {ref: zone for ref, zone in result_state.component_zone_map}
    assert zone_map["Q1"] == "HV"
    assert zone_map["C1"] == "Power"
    assert zone_map["U_MCU1"] == "MCU"
    assert zone_map["R1"] == "Signal"
