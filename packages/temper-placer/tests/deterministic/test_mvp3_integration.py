"""
End-to-end integration test for MVP-3: Deterministic Zone-Based Placement.

Tests the full pipeline: Zone Geometry → Zone Assignment → Slot Generation → 
Component Assignment → Sequential Routing (MVP-2).
"""

import pytest
from temper_placer.deterministic import DeterministicPipeline, BoardState
from temper_placer.deterministic.stages import (
    ZoneGeometryStage,
    ZoneAssignmentStage,
    SlotGenerationStage,
    ComponentAssignmentStage,
    ApplyPlacementsStage,
    ClearanceGridStage,
    NetOrderingStage,
    SequentialRoutingStage
)
from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist, Component, Net, Pin
from temper_placer.core.design_rules import DesignRules, NetClassRules


def test_mvp3_end_to_end():
    """Full MVP-3 pipeline: zone-based placement + routing."""
    # Setup: Board with components from different zones
    board = Board(width=100, height=100)
    
    # HV component (should go to left 30%)
    c_hv = Component(
        ref="Q1",
        footprint="TO-247",
        bounds=(5, 5),
        pins=[Pin("1", "C", (0, 0), net="AC_L")],
        initial_position=(None, None)  # Will be placed by MVP-3
    )
    
    # Power component (should go to 30-60%)
    c_power = Component(
        ref="C1",
        footprint="CAP_1210",
        bounds=(3, 3),
        pins=[Pin("1", "1", (0, 0), net="VBUS"), Pin("2", "2", (1, 0), net="GND")],
        initial_position=(None, None)
    )
    
    # Signal components (should go to 60-90%)
    c_sig1 = Component(
        ref="R1",
        footprint="0603",
        bounds=(1.6, 0.8),
        pins=[Pin("1", "1", (0, 0), net="SENSE"), Pin("2", "2", (0.8, 0), net="GND")],
        initial_position=(None, None)
    )
    c_sig2 = Component(
        ref="R2",
        footprint="0603",
        bounds=(1.6, 0.8),
        pins=[Pin("1", "1", (0, 0), net="SENSE"), Pin("2", "2", (0.8, 0), net="3V3")],
        initial_position=(None, None)
    )
    
    # MCU component (should go to right 10%)
    c_mcu = Component(
        ref="U_MCU1",
        footprint="QFN56",
        bounds=(9, 9),
        pins=[Pin("1", "VDD", (0, 0), net="3V3")],
        initial_position=(None, None)
    )
    
    nets = [
        Net("AC_L", [("Q1", "C")], net_class="HighVoltage"),
        Net("VBUS", [("C1", "1")], net_class="Power"),
        Net("GND", [("C1", "2"), ("R1", "2")], net_class="Signal"),
        Net("SENSE", [("R1", "1"), ("R2", "1")], net_class="Signal"),
        Net("3V3", [("R2", "2"), ("U_MCU1", "VDD")], net_class="Signal"),
    ]
    
    netlist = Netlist(components=[c_hv, c_power, c_sig1, c_sig2, c_mcu], nets=nets)
    initial_state = BoardState(board=board, netlist=netlist)
    
    #  Pipeline: MVP-3 Placement + MVP-2 Routing
    design_rules = DesignRules()
    design_rules.net_classes = {
        "HighVoltage": NetClassRules("HighVoltage", trace_width=0.5, clearance=2.0, via_diameter=0.8, via_drill=0.4),
        "Power": NetClassRules("Power", trace_width=0.4, clearance=0.3, via_diameter=0.7, via_drill=0.35),
        "Signal": NetClassRules("Signal", trace_width=0.2, clearance=0.2, via_diameter=0.6, via_drill=0.3)
    }
    
    pipeline = DeterministicPipeline(stages=[
        # Phase 1-4: MVP-3 Placement
        ZoneGeometryStage(),
        ZoneAssignmentStage(),
        SlotGenerationStage(slot_spacing_mm=5.0),
        ComponentAssignmentStage(),
        ApplyPlacementsStage(),  # Apply placements to Component.initial_position
        # Phase 5: MVP-2 Routing
        ClearanceGridStage(cell_size_mm=0.5),
        NetOrderingStage(),
        SequentialRoutingStage(design_rules=design_rules)
    ])
    
    final_state = pipeline.run(initial_state)
    
    # ========== VERIFY PLACEMENT ==========
    
    # 1. All components placed
    placements = dict(final_state.placements)
    assert len(placements) == 5
    assert "Q1" in placements
    assert "C1" in placements
    assert "R1" in placements
    assert "R2" in placements
    assert "U_MCU1" in placements
    
    # 2. No overlaps (all unique positions)
    positions = list(placements.values())
    assert len(positions) == len(set(positions))
    
    # 3. Zone constraints met
    # HV (Q1) should be in left 30% (x < 30)
    hv_x = placements["Q1"][0]
    assert hv_x < 30, f"HV component Q1 at x={hv_x}, should be < 30"
    
    # MCU (U_MCU1) should be in right 10% (x > 90)
    mcu_x = placements["U_MCU1"][0]
    assert mcu_x > 90, f"MCU component U_MCU1 at x={mcu_x}, should be > 90"
    
    # Power (C1) should be in 30-60%
    power_x = placements["C1"][0]
    assert 30 <= power_x < 60, f"Power component C1 at x={power_x}, should be 30-60"
    
    # Signal (R1, R2) should be in 60-90%
    sig1_x = placements["R1"][0]
    sig2_x = placements["R2"][0]
    assert 60 <= sig1_x < 90, f"Signal component R1 at x={sig1_x}, should be 60-90"
    assert 60 <= sig2_x < 90, f"Signal component R2 at x={sig2_x}, should be 60-90"
    
    # ========== VERIFY ROUTING ==========
    
    # 4. Routing succeeded for at least some nets
    routes = list(final_state.routes)
    assert len(routes) > 0, "No routes generated"
    
    # Check that at least SENSE net routed (connects R1 and R2 in same zone)
    sense_routes = [r for r in routes if r.net == "SENSE"]
    assert len(sense_routes) > 0, "SENSE net failed to route"


def test_mvp3_determinism():
    """Verify MVP-3 produces same placement every time."""
    board = Board(width=100, height=100)
    
    c1 = Component(ref="R1", footprint="0603", bounds=(1.6, 0.8),
                   pins=[Pin("1", "1", (0, 0), net="N1")], initial_position=(None, None))
    c2 = Component(ref="R2", footprint="0603", bounds=(1.6, 0.8),
                   pins=[Pin("1", "1", (0, 0), net="N1")], initial_position=(None, None))
    nets = [Net("N1", [("R1", "1"), ("R2", "1")], net_class="Signal")]
    netlist = Netlist(components=[c1, c2], nets=nets)
    
    def run_mvp3():
        initial_state = BoardState(board=board, netlist=netlist)
        pipeline = DeterministicPipeline(stages=[
            ZoneGeometryStage(),
            ZoneAssignmentStage(),
            SlotGenerationStage(slot_spacing_mm=5.0),
            ComponentAssignmentStage()
        ])
        return dict(pipeline.run(initial_state).placements)
    
    placements1 = run_mvp3()
    placements2 = run_mvp3()
    
    assert placements1 == placements2
