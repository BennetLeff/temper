"""
Tests for Router V6 Stage 4.4: Assign Trace Widths

Part of temper-eixu
"""

import pytest

from temper_placer.router_v6.astar_pathfinding import PathfindingResult, RoutePath
from temper_placer.router_v6.trace_width_assignment import (
    TraceWidth,
    TraceWidthAssignment,
    assign_trace_widths,
)


def test_assign_no_widths():
    """Test width assignment with no paths."""
    result = PathfindingResult(routed_paths={}, failed_nets=[])
    
    assignment = assign_trace_widths(result)
    
    assert assignment.assignment_count == 0


def test_assign_default_width():
    """Test default width assignment for signal nets."""
    path = RoutePath("SIG_1", [(0, 0), (10, 10)], "F.Cu", 14.1)
    result = PathfindingResult(routed_paths={"SIG_1": path}, failed_nets=[])
    
    assignment = assign_trace_widths(result, default_width=0.127)
    
    assert assignment.assignment_count == 1
    width = assignment.get_width("SIG_1")
    assert width == 0.127


def test_assign_power_width():
    """Test power net width assignment."""
    gnd_path = RoutePath("GND", [(0, 0), (10, 10)], "F.Cu", 14.1)
    vcc_path = RoutePath("VCC", [(5, 5), (15, 15)], "F.Cu", 14.1)
    
    result = PathfindingResult(
        routed_paths={"GND": gnd_path, "VCC": vcc_path},
        failed_nets=[],
    )
    
    assignment = assign_trace_widths(result, power_width=0.508)
    
    # Both power nets should get power width
    assert assignment.get_width("GND") == 0.508
    assert assignment.get_width("VCC") == 0.508


def test_assign_hv_width():
    """Test high voltage net width assignment."""
    ac_path = RoutePath("AC_L", [(0, 0), (10, 10)], "F.Cu", 14.1)
    result = PathfindingResult(routed_paths={"AC_L": ac_path}, failed_nets=[])
    
    assignment = assign_trace_widths(result, hv_width=0.635)
    
    # HV net should get HV width
    assert assignment.get_width("AC_L") == 0.635


def test_trace_width_dataclass():
    """Test TraceWidth dataclass."""
    width = TraceWidth(
        net_name="TEST_NET",
        width_mm=0.254,
        reason="Custom requirement",
    )
    
    assert width.net_name == "TEST_NET"
    assert width.width_mm == 0.254
    assert width.reason == "Custom requirement"


def test_trace_width_assignment_dataclass():
    """Test TraceWidthAssignment dataclass."""
    width1 = TraceWidth("NET1", 0.127, "Signal")
    width2 = TraceWidth("NET2", 0.508, "Power")
    
    assignment = TraceWidthAssignment(assignments={
        "NET1": width1,
        "NET2": width2,
    })
    
    assert assignment.assignment_count == 2
    assert assignment.get_width("NET1") == 0.127
    assert assignment.get_width("NET2") == 0.508
    assert assignment.get_width("NET3") is None


def test_assign_gate_drive_width():
    """Test gate drive signal width assignment."""
    gate_path = RoutePath("GATE_H", [(0, 0), (10, 10)], "F.Cu", 14.1)
    result = PathfindingResult(routed_paths={"GATE_H": gate_path}, failed_nets=[])
    
    assignment = assign_trace_widths(result, power_width=0.508)
    
    # Gate drive should get 60% of power width
    expected_width = 0.508 * 0.6
    assert assignment.get_width("GATE_H") == pytest.approx(expected_width)


def test_assign_multiple_net_classes():
    """Test width assignment for mixed net classes."""
    paths = {
        "SIG1": RoutePath("SIG1", [(0, 0)], "F.Cu", 0),
        "GND": RoutePath("GND", [(1, 1)], "F.Cu", 0),
        "AC_L": RoutePath("AC_L", [(2, 2)], "F.Cu", 0),
        "GATE_H": RoutePath("GATE_H", [(3, 3)], "F.Cu", 0),
    }
    
    result = PathfindingResult(routed_paths=paths, failed_nets=[])
    
    assignment = assign_trace_widths(
        result,
        default_width=0.127,
        power_width=0.508,
        hv_width=0.635,
    )
    
    # Each net class should get appropriate width
    assert assignment.get_width("SIG1") == 0.127  # Signal
    assert assignment.get_width("GND") == 0.508  # Power
    assert assignment.get_width("AC_L") == 0.635  # HV
    assert assignment.get_width("GATE_H") == pytest.approx(0.3048)  # Gate (60% of power)
