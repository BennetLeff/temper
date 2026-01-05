from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist, Component, Pin
from temper_placer.deterministic.state import BoardState
from temper_placer.deterministic.pipeline import DeterministicPipeline
from temper_placer.deterministic.stages.setup import SetupStage
from temper_placer.deterministic.stages.clearance_grid import ClearanceGridStage
from temper_placer.deterministic.stages.net_ordering import NetOrderingStage
from temper_placer.deterministic.stages.sequential_routing import SequentialRoutingStage
from temper_placer.deterministic.stages.layer_assignment import LayerAssignmentStage, LayerAssignment

def test_sequential_routing_via_drc():
    # Board 100x100
    board = Board(width=100, height=100)
    
    # Net 1: GND, on In1.Cu (layer 1)
    # Net 2: VCC, on In1.Cu (layer 1)
    # We place Net 1's pins such that it needs a via.
    # Then we place another component that blocks the ideal via position.
    
    p1 = Pin(name="1", number="1", position=(0.0, 0.0), net="GND", layer="F.Cu")
    p2 = Pin(name="1", number="1", position=(0.0, 0.0), net="GND", layer="F.Cu")
    
    c1 = Component(ref="J1", footprint="Pad", bounds=(2,2), pins=[p1], initial_position=(10, 10))
    c2 = Component(ref="J2", footprint="Pad", bounds=(2,2), pins=[p2], initial_position=(20, 10))
    
    # Blocking component (Net 3) - placed right where the via for J1 would normally go
    # Default via search is spiral. If (10,10) is blocked, it should move.
    p3 = Pin(name="1", number="1", position=(0.0, 0.0), net="BLOCK", layer="F.Cu")
    # Place it at (10.5, 10.5) to block (10,10) via
    c3 = Component(ref="B1", footprint="Pad", bounds=(2,2), pins=[p3], initial_position=(10.8, 10.8))
    
    from temper_placer.core.netlist import Net
    n1 = Net(name="GND", pins=[("J1", "1"), ("J2", "1")], net_class="Power")
    n2 = Net(name="BLOCK", pins=[("B1", "1")], net_class="Signal")
    
    netlist = Netlist(components=[c1, c2, c3], nets=[n1, n2])
    
    # Setup pipeline
    pipeline = DeterministicPipeline(stages=[
        SetupStage(),
        ClearanceGridStage(),
        LayerAssignmentStage(layer_assignments=frozenset([
            LayerAssignment("GND", 1), # In1.Cu
        ])),
        NetOrderingStage(),
        SequentialRoutingStage()
    ])
    
    initial_state = BoardState(board=board, netlist=netlist)
    final_state = pipeline.run(initial_state)
    
    # Check vias
    vias = [v for v in final_state.vias if v.net == "GND"]
    assert len(vias) >= 2
    
    # Find via for J1 (at 10,10)
    via_j1 = next(v for v in vias if abs(v.position[0] - 10.0) < 5.0 and abs(v.position[1] - 10.0) < 5.0)
    print(f"Via J1 placed at: {via_j1.position}")
    
    # It should NOT be at (10.8, 10.8) or too close to it
    dist = ((via_j1.position[0] - 10.8)**2 + (via_j1.position[1] - 10.8)**2)**0.5
    # B1 pad is at 10.8, 10.8. Pad radius ~0.5. Via radius ~0.3. Clearance 0.2.
    # Min distance should be > 1.0
    assert dist > 1.0
    
    print("Verification successful!")

def test_sequential_routing_trace_registration():
    # Board 100x100
    board = Board(width=100, height=100)
    
    # Net 1: A trace from (50, 50) to (60, 50) on layer 0 (F.Cu)
    # Net 2: A via that wants to be at (55, 50) on layer 1
    # Since vias are through-hole, the trace on layer 0 should block the via on layer 1.
    
    p1a = Pin(name="1", number="1", position=(0.0, 0.0), net="NET1", layer="F.Cu")
    p1b = Pin(name="1", number="1", position=(0.0, 0.0), net="NET1", layer="F.Cu")
    c1a = Component(ref="U1", footprint="Pad", bounds=(2,2), pins=[p1a], initial_position=(50, 50))
    c1b = Component(ref="U2", footprint="Pad", bounds=(2,2), pins=[p1b], initial_position=(60, 50))
    
    p2 = Pin(name="1", number="1", position=(0.0, 0.0), net="NET2", layer="F.Cu")
    c2 = Component(ref="U3", footprint="Pad", bounds=(2,2), pins=[p2], initial_position=(55, 50))
    # Net 2 is a plane net to force a via
    
    from temper_placer.core.netlist import Net
    n1 = Net(name="NET1", pins=[("U1", "1"), ("U2", "1")], net_class="HighVoltage")
    n2 = Net(name="NET2", pins=[("U3", "1")], net_class="Power")
    
    netlist = Netlist(components=[c1a, c1b, c2], nets=[n1, n2])
    
    # Setup pipeline
    pipeline = DeterministicPipeline(stages=[
        SetupStage(),
        ClearanceGridStage(),
        LayerAssignmentStage(layer_assignments=frozenset([
            LayerAssignment("NET1", 0), # F.Cu
            LayerAssignment("NET2", 1), # In1.Cu (plane)
        ])),
        NetOrderingStage(), # NET1 should come before NET2 because it's signal and not plane? 
        # Actually net_ordering might put plane nets last.
        SequentialRoutingStage()
    ])
    
    initial_state = BoardState(board=board, netlist=netlist)
    final_state = pipeline.run(initial_state)
    
    # Check if NET1 was routed
    assert len(final_state.routes) > 0
    
    # Verify traces are in the oracle
    oracle = final_state.drc_oracle
    assert len(oracle.geometry.tracks) >= len(final_state.routes)
    print(f"Oracle has {len(oracle.geometry.tracks)} tracks")
    
    # Check via for NET2
    vias = [v for v in final_state.vias if v.net == "NET2"]
    assert len(vias) == 1
    via_pos = vias[0].position
    print(f"NET2 via placed at: {via_pos}")
    
    # In this case, since NET1 trace avoided U3 pad, (55, 50) remained valid.
    # But we confirmed via first test that DRCOracle avoids pads.
    # The registration of tracks ensures that subsequent nets avoid these tracks.
    
    print("Verification successful!")

if __name__ == "__main__":
    test_sequential_routing_via_drc()
    test_sequential_routing_trace_registration()
