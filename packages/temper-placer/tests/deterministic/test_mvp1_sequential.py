
import pytest
from temper_placer.deterministic.pipeline import DeterministicPipeline
from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid
from temper_placer.deterministic.stages.astar import DeterministicAStar
from temper_placer.routing.net_ordering import order_nets
from temper_placer.core.netlist import Netlist, Component, Net, Pin
from temper_placer.core.board import Board
from temper_placer.core.loop import LoopCollection

def test_route_5_nets_sequentially():
    # 1. Setup a board with 5 simple nets that could potentially conflict
    # 50x50mm board
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
    loops = LoopCollection()
    
    # 2. Order nets
    ordered_nets = order_nets(netlist, loops)
    assert len(ordered_nets) == 5
    
    # 3. Initialize grid
    grid = ClearanceGrid(width_mm=50, height_mm=50, cell_size_mm=0.5)
    
    # Block all pads first
    for comp in components:
        for pin in comp.pins:
            pos = (comp.initial_position[0] + pin.position[0], 
                   comp.initial_position[1] + pin.position[1])
            grid.block_circle(pos, radius_mm=0.5, clearance_mm=0.2)
            
    # 4. Route sequentially
    results = {}
    for net_name in ordered_nets:
        # Find pin positions
        net = next(n for n in nets if n.name == net_name)
        pin_positions = []
        for ref, pin_name in net.pins:
            comp = next(c for c in components if c.ref == ref)
            pin = next(p for p in comp.pins if p.name == pin_name)
            pos = (comp.initial_position[0] + pin.position[0], 
                   comp.initial_position[1] + pin.position[1])
            pin_positions.append(pos)
            # Temporarily unblock target pins
            grid.unblock_circle(pos, radius_mm=0.5)
            
        pathfinder = DeterministicAStar(grid)
        path = pathfinder.find_path(start=pin_positions[0], end=pin_positions[1])
        
        assert path is not None, f"Failed to route {net_name}"
        results[net_name] = path
        
        # BLOCK the routed trace so next nets can't use it
        grid.block_trace(path, width_mm=0.25, clearance_mm=0.2)
        
        # Re-block the pins (except they are now blocked by trace anyway, 
        # but let's be explicit about the pad body)
        for pos in pin_positions:
             grid.block_circle(pos, radius_mm=0.5, clearance_mm=0.2)

    assert len(results) == 5
    print("Successfully routed 5 nets sequentially with zero conflicts!")

if __name__ == "__main__":
    test_route_5_nets_sequentially()
