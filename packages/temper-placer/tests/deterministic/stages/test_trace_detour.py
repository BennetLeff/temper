from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist, Component, Pin, Net
from temper_placer.deterministic.state import BoardState
from temper_placer.deterministic.pipeline import DeterministicPipeline
from temper_placer.deterministic.stages.setup import SetupStage
from temper_placer.deterministic.stages.clearance_grid import ClearanceGridStage
from temper_placer.deterministic.stages.net_ordering import NetOrderingStage
from temper_placer.deterministic.stages.sequential_routing import SequentialRoutingStage
from temper_placer.deterministic.stages.layer_assignment import LayerAssignmentStage, LayerAssignment

def test_trace_detour_via_oracle():
    # Board 100x100
    board = Board(width=100, height=100)
    
    # Net 1: Start (10, 10), End (30, 10)
    # Obstacle: Pad at (20, 10) belonging to another net
    
    p1a = Pin(name="1", number="1", position=(0.0, 0.0), net="NET1", layer="F.Cu")
    p1b = Pin(name="1", number="1", position=(0.0, 0.0), net="NET1", layer="F.Cu")
    c1a = Component(ref="U1", footprint="Pad", bounds=(2,2), pins=[p1a], initial_position=(10, 10))
    c1b = Component(ref="U2", footprint="Pad", bounds=(2,2), pins=[p1b], initial_position=(30, 10))
    
    p_obs = Pin(name="1", number="1", position=(0.0, 0.0), net="OBS", layer="F.Cu")
    # Obstacle at (20, 10)
    c_obs = Component(ref="OBS", footprint="Pad", bounds=(4,4), pins=[p_obs], initial_position=(20, 10))
    
    n1 = Net(name="NET1", pins=[("U1", "1"), ("U2", "1")], net_class="Signal")
    n_obs = Net(name="OBS", pins=[("OBS", "1")], net_class="Signal")
    
    netlist = Netlist(components=[c1a, c1b, c_obs], nets=[n1, n_obs])
    
    # Setup pipeline
    pipeline = DeterministicPipeline(stages=[
        SetupStage(),
        ClearanceGridStage(cell_size_mm=0.5), # Grid is empty
        LayerAssignmentStage(layer_assignments=frozenset([
            LayerAssignment("NET1", 0),
            LayerAssignment("OBS", 0),
        ])),
        NetOrderingStage(),
        SequentialRoutingStage()
    ])
    
    initial_state = BoardState(board=board, netlist=netlist)
    final_state = pipeline.run(initial_state)
    
    # Check the path of NET1
    routes = [r for r in final_state.routes if r.net == "NET1"]
    assert len(routes) > 0
    
    # Any segment of NET1 should NOT pass through the obstacle at (20, 10)
    # The obstacle pad has bounds (4,4) -> radius ~2.0. Clearance 0.2. 
    # So any point on the trace should be at least ~2.2mm away from (20, 10).
    
    for r in routes:
        # Distance from (20, 10) to segment (r.start, r.end)
        from temper_placer.routing.constraints.geometry import Point, LineSegment, point_to_segment_distance
        dist = point_to_segment_distance(Point(20, 10), LineSegment(Point(*r.start), Point(*r.end)))
        print(f"Segment from {r.start} to {r.end}, distance to obstacle: {dist:.3f}")
        assert dist > 1.0 # Should definitely be > 1.0 if it detoured
        
    print("Detour verification successful!")

if __name__ == "__main__":
    test_trace_detour_via_oracle()
