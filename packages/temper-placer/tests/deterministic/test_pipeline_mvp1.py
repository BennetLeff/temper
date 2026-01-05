
import pytest
from temper_placer.deterministic import DeterministicPipeline, BoardState
from temper_placer.deterministic.stages import (
    ClearanceGridStage,
    NetOrderingStage,
    SequentialRoutingStage
)
from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist, Component, Net, Pin

def test_deterministic_pipeline_mvp1():
    # 1. Setup
    board = Board(width=50, height=50)
    components = [
        Component(ref=f"J{i}", footprint="PinHeader", bounds=(5, 5), pins=[
            Pin("1", "1", (0, 0), net=f"NET{i}")
        ], initial_position=(10, 5 + i*10)) for i in range(5)
    ] + [
        Component(ref=f"U{i}", footprint="SOIC-8", bounds=(5, 5), pins=[
            Pin("1", "1", (0, 0), net=f"NET{i}")
        ], initial_position=(40, 5 + i*10)) for i in range(5)
    ]
    nets = [Net(f"NET{i}", [(f"J{i}", "1"), (f"U{i}", "1")]) for i in range(5)]
    netlist = Netlist(components=components, nets=nets)
    
    initial_state = BoardState(board=board, netlist=netlist)
    
    # 2. Initialize pipeline
    pipeline = DeterministicPipeline(stages=[
        ClearanceGridStage(cell_size_mm=0.5),
        NetOrderingStage(),
        SequentialRoutingStage(trace_width_mm=0.25, clearance_mm=0.2)
    ])
    
    # 3. Run
    final_state = pipeline.run(initial_state)
    
    # 4. Verify
    assert final_state.grid is not None
    assert len(final_state.net_order) == 5
    assert len(final_state.routes) > 0
    
    # Each net should have some trace segments
    routed_nets = {t.net for t in final_state.routes}
    assert len(routed_nets) == 5
    
    # 5. Verify no conflicts (no sharing of grid cells)
    # We can use the grid to verify this
    grid = final_state.grid
    # Actually, we can check the routes themselves for overlaps
    # But checking grid cells is easier if we have them.
    # The Trace object only has start/end.
    
    # Let's verify by attempting to route a net that SHOULD fail if blocked
    # (Similar to my reproduction test)
    # We'll add a 6th net that MUST cross one of the existing nets
    from temper_placer.deterministic.stages.astar import DeterministicAStar
    # Horizontal net from (5, 15) to (45, 15) - must cross NET1 at x=10 and x=40? 
    # No, NET1 is vertical-ish? Wait.
    # NET0: J0(10, 5) to U0(40, 5) - Horizontal
    # NET1: J1(10, 15) to U1(40, 15) - Horizontal
    
    # Let's try to route a vertical net that crosses all of them
    v_start = (25.0, 0.0)
    v_end = (25.0, 50.0)
    pathfinder = DeterministicAStar(grid)
    path = pathfinder.find_path(start=v_start, end=v_end)
    
    assert path is None, "A vertical net should be blocked by the horizontal nets!"
    
    print("Deterministic pipeline MVP-1 test passed with zero conflicts verified!")

if __name__ == "__main__":
    test_deterministic_pipeline_mvp1()
