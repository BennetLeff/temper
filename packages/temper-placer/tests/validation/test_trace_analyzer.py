import pytest
from temper_placer.core.board import Board, Trace
from temper_placer.validation.trace_analyzer import (
    calculate_actual_trace_length, 
    calculate_actual_loop_area,
    calculate_min_hv_lv_clearance
)

def test_trace_length():
    board = Board(width=100, height=100)
    # L-shaped trace for net "N1"
    board.traces = [
        Trace(start=(0, 0), end=(10, 0), width=0.2, layer="F.Cu", net="N1"),
        Trace(start=(10, 0), end=(10, 10), width=0.2, layer="F.Cu", net="N1"),
    ]
    
    length = calculate_actual_trace_length(board, "N1")
    assert length == pytest.approx(20.0)

def test_loop_area_from_traces():
    board = Board(width=100, height=100)
    # 10x10 square loop
    board.traces = [
        Trace(start=(0, 0), end=(10, 0), width=0.2, layer="F.Cu", net="L1"),
        Trace(start=(10, 0), end=(10, 10), width=0.2, layer="F.Cu", net="L1"),
        Trace(start=(10, 10), end=(0, 10), width=0.2, layer="F.Cu", net="L1"),
        Trace(start=(0, 10), end=(0, 0), width=0.2, layer="F.Cu", net="L1"),
    ]
    
    area = calculate_actual_loop_area(board, ["L1"])
    # Convex hull of (0,0), (10,0), (10,10), (0,10) is 100.0
    assert area == pytest.approx(100.0)

def test_hv_lv_trace_clearance():
    board = Board(width=100, height=100)
    board.traces = [
        Trace(start=(0, 0), end=(10, 0), width=0.2, layer="F.Cu", net="HV"),
        Trace(start=(0, 20), end=(10, 20), width=0.2, layer="F.Cu", net="LV"),
    ]
    
    net_classes = {"HV": "HighVoltage", "LV": "Signal"}
    clearance = calculate_min_hv_lv_clearance(board, net_classes)
    
    # Shortest dist between (0,0)-(10,0) and (0,20)-(10,20) is 20.0
    assert clearance == pytest.approx(20.0)
