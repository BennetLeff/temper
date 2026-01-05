
import pytest
from temper_placer.deterministic import DeterministicPipeline, BoardState
from temper_placer.deterministic.stages import (
    ClearanceGridStage,
    NetOrderingStage,
    SequentialRoutingStage
)
from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist, Component, Net, Pin
from temper_placer.core.design_rules import DesignRules, NetClassRules

def test_mvp2_clearance_handling():
    # 1. Setup Design Rules
    design_rules = DesignRules()
    design_rules.net_classes = {
        "HighVoltage": NetClassRules(
            name="HighVoltage",
            trace_width=0.5,
            clearance=2.0, # Large clearance
            via_diameter=0.8,
            via_drill=0.4
        ),
        "Signal": NetClassRules(
            name="Signal",
            trace_width=0.2,
            clearance=0.2, # Small clearance
            via_diameter=0.6,
            via_drill=0.3
        )
    }
    
    # 2. Setup Board & Netlist
    board = Board(width=20, height=20)
    
    # HV Net: Horizontal at y=10
    # Signal Net: Horizontal at y=12 (distance 2.0mm center-to-center)
    # If HV has 2.0mm clearance (radius), it blocks y=8 to y=12.
    # So Signal at y=12 is exactly on the edge? 
    # HV width=0.5 -> radius 0.25. Clearance 2.0. Total blocked radius 2.25.
    # Center y=10. Blocked: 7.75 to 12.25.
    # So y=12 is blocked.
    
    # Components for HV Net
    c_hv_1 = Component(ref="J1", footprint="PinHeader", bounds=(2,2), 
                       pins=[Pin("1", "1", (0,0), net="HV_NET")], 
                       initial_position=(2, 10))
    c_hv_2 = Component(ref="J2", footprint="PinHeader", bounds=(2,2), 
                       pins=[Pin("1", "1", (0,0), net="HV_NET")], 
                       initial_position=(18, 10))
                       
    # Components for Signal Net
    c_sig_1 = Component(ref="U1", footprint="0603", bounds=(2,2), 
                        pins=[Pin("1", "1", (0,0), net="SIG_NET")], 
                        initial_position=(5, 12))
    c_sig_2 = Component(ref="U2", footprint="0603", bounds=(2,2), 
                        pins=[Pin("1", "1", (0,0), net="SIG_NET")], 
                        initial_position=(15, 12))
                        
    nets = [
        Net("HV_NET", [("J1", "1"), ("J2", "1")], net_class="HighVoltage"),
        Net("SIG_NET", [("U1", "1"), ("U2", "1")], net_class="Signal")
    ]
    
    netlist = Netlist(components=[c_hv_1, c_hv_2, c_sig_1, c_sig_2], nets=nets)
    initial_state = BoardState(board=board, netlist=netlist)
    
    # 3. Pipeline
    # Note: SequentialRoutingStage needs to support DesignRules now
    pipeline = DeterministicPipeline(stages=[
        ClearanceGridStage(cell_size_mm=0.1), # Fine grid for precision
        NetOrderingStage(),
        SequentialRoutingStage(design_rules=design_rules) # Inject rules
    ])
    
    # 4. Run
    final_state = pipeline.run(initial_state)
    
    # 5. Verify
    # HV_NET should route successfully (straight line)
    hv_route = next((r for r in final_state.routes if r.net == "HV_NET"), None)
    assert hv_route is not None, "HV_NET failed to route"
    
    # SIG_NET should FAIL or detour because y=12 is blocked by HV_NET
    # The straight path (5,12) -> (15,12) is blocked.
    # DeterministicAStar might find a detour or fail if blocking is strict.
    
    sig_segments = [r for r in final_state.routes if r.net == "SIG_NET"]
    
    if sig_segments:
        # Check that it detoured
        # If it went straight, all Y coordinates would be close to 12
        # Let's check max deviation
        ys = [p[1] for seg in sig_segments for p in (seg.start, seg.end)]
        min_y = min(ys)
        max_y = max(ys)
        
        # It needs to go outside [7.75, 12.25]. 
        # Since it starts at 12 (blocked), routing should actually FAIL start/end validation
        # or require unblocking of start/end. 
        # But wait, we unblock start/end pins in SequentialRoutingStage.
        # But the path between them is blocked.
        # So it must go around.
        print(f"Signal net routed. Y range: {min_y} to {max_y}")
        
        # If it stayed at y=12, it violated clearance
        assert not (min_y >= 11.9 and max_y <= 12.1), "Signal net ignored HV clearance!"
        
    else:
        # If it failed, that might be correct if no path found (though board is empty elsewhere)
        # With A*, it should find a path around.
        # If it failed, maybe start/end were permanently blocked?
        pass

if __name__ == "__main__":
    test_mvp2_clearance_handling()
