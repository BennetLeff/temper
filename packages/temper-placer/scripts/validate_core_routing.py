#!/usr/bin/env python3
"""
Minimal validation script for core routing pipeline (temper-2edy.1).
Routes one single net and exports to KiCad.
"""

import sys
import time
from pathlib import Path
import jax.numpy as jnp
import numpy as np

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root / "packages/temper-placer/src"))

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist, Component, Pin, Net
from temper_placer.router_v6.adapter import MazeRouter
from temper_placer.router_v6.layer_assignment import LayerAssignment, Layer
from temper_placer.io.trace_writer import write_traces_to_pcb
from temper_placer.io.kicad_parser import parse_kicad_pcb

def main():
    template_pcb = project_root / "pcb/temper.kicad_pcb"
    output_pcb = project_root / "packages/temper-placer/minimal_route.kicad_pcb"

    if not template_pcb.exists():
        print(f"Error: Template {template_pcb} not found")
        sys.exit(1)

    print(f"Parsing {template_pcb}...")
    parse_result = parse_kicad_pcb(template_pcb)
    netlist = parse_result.netlist
    board = parse_result.board

    # Phase 4 Configuration: Power Isolation (temper-2edy.12)
    target_net_name = "AC_L"
    target_net = next((n for n in netlist.nets if n.name == target_net_name), None)
    
    # AC_L Connects J_AC_IN (Pin 1) to D1 (Pin 1)
    # J_AC_IN is at (10, 75). Pin 1 at (0, 0)
    # D1 is at (30, 30). Pin 1 at (0, 0)
    test_pins = [(10.0, 75.0), (30.0, 30.0)]

    print(f"Targeting net: {target_net.name}")

    # Extract component positions
    positions = jnp.array([
        (c.initial_position[0], c.initial_position[1])
        if c.initial_position else (0.0, 0.0)
        for c in netlist.components
    ])

    # Initialize Router (Phase 4 requirements: Coarser grid but high clearance)
    cell_size = 0.2 # mm
    print(f"Initializing MazeRouter (cell_size={cell_size}mm, clearance=1.0mm for isolation)...")
    router = MazeRouter.from_board(
        board, 
        cell_size_mm=cell_size, 
        num_layers=4, 
        min_clearance=1.0 # mm (Reduced from 3.0 to find a path)
    )

    print("Blocking components...")
    router.block_components(netlist.components, positions, margin=0.1, layer_specific=True)

    print("Blocking pads...")
    # Using larger margin for power nets to ensure isolation
    router.block_pads(netlist.components, positions, netlist, trace_width=0.5, clearance=0.2)

    # Prepare pin positions for the target net
    pin_positions = []
    for comp_ref, pin_name in target_net.pins:
        comp = netlist.get_component(comp_ref)
        pin = comp.get_pin(pin_name)
        comp_idx = netlist.get_component_index(comp_ref)
        comp_pos = positions[comp_idx]
        
        # Simple absolute position calculation
        # We should account for rotation index 0, 1, 2, 3 (0, 90, 180, 270)
        angle = 0.0
        if comp.initial_rotation is not None:
             angle = comp.initial_rotation * (np.pi / 2.0)
        
        abs_pos = pin.absolute_position(
            (float(comp_pos[0]), float(comp_pos[1])),
            angle
        )
        pin_positions.append(abs_pos)

    print(f"Routing {target_net.name} between {pin_positions}...")
    
    assignment = LayerAssignment(
        net=target_net.name, 
        primary_layer=Layer.L1_TOP, 
        allowed_layers=[Layer.L1_TOP, Layer.L4_BOT]
    )
    
    start_time = time.perf_counter()
    # Mocking cost_map as None
    result = router.route_net(target_net.name, pin_positions, assignment)
    elapsed = (time.perf_counter() - start_time) * 1000
    
    if result.success:
        print(f"Routing successful! ({elapsed:.2f}ms)")
        print(f"Path length: {result.length:.2f}mm, Vias: {result.via_count}")
        
        # Write to PCB
        routing_results = {target_net.name: result}
        items_added = write_traces_to_pcb(
            template_pcb=template_pcb,
            output_pcb=output_pcb,
            routing_results=routing_results,
            cell_size=cell_size,
            netlist=netlist,
            default_trace_width=0.1 # Match Phase 3 breakout narrow width
        )
        print(f"Exported {items_added} items to {output_pcb}")

        # Add grid visualization
        visual_pcb = output_pcb.with_name("minimal_route_visual.kicad_pcb")
        visualize_occupancy(router, output_pcb, visual_pcb)
    else:
        print(f"Routing failed: {result.failure_reason}")

def visualize_occupancy(router, template_pcb, output_pcb):
    from kiutils.board import Board as KiBoard
    from kiutils.items.gritems import GrRect
    from kiutils.items.common import Position
    import uuid

    board = KiBoard.from_file(str(template_pcb))
    
    # Visualize all layers, but distinct colors/layers if possible?
    # For now just Dwgs.User for Layer 0
    layer_idx = 0 
    cell_size = router.cell_size
    origin = router.origin
    
    print(f"Visualizing occupancy for layer {layer_idx} on Dwgs.User...")
    
    count = 0
    for x in range(router.grid_size[0]):
        for y in range(router.grid_size[1]):
            if router.occupancy[x, y, layer_idx] == -1:
                x1 = origin[0] + x * cell_size
                y1 = origin[1] + y * cell_size
                x2 = x1 + cell_size * 0.8
                y2 = y1 + cell_size * 0.8
                
                rect = GrRect(
                    start=Position(X=x1, Y=y1),
                    end=Position(X=x2, Y=y2),
                    layer="Dwgs.User",
                    width=0.01,
                    tstamp=str(uuid.uuid4())
                )
                board.graphicItems.append(rect)
                count += 1
                
    board.to_file(str(output_pcb))
    print(f"Added {count} visualization rectangles to {output_pcb}")

if __name__ == "__main__":
    main()
