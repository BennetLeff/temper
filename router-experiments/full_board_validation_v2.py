#!/usr/bin/env python3
"""
Full Board Validation v2
Routes the real Temper board using CSpaceRoutingPipeline to verify Trace Crossing and Zone Bleeding fixes.
"""

import os
import sys
import logging
import time
from pathlib import Path

# Add package root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.trace_writer import write_traces_to_pcb
from temper_placer.routing.c_space_pipeline import CSpaceRoutingPipeline, PipelineConfig
from temper_placer.routing.net_ordering import order_nets
from temper_placer.core.loop import LoopCollection
from temper_placer.io.kicad_writer import write_placements_to_pcb, PlacementUpdate

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def run_full_validation():
    input_pcb = Path("pcb/temper_placed.kicad_pcb")
    output_pcb = Path("pcb/temper_routed_v2.kicad_pcb")
    
    if not input_pcb.exists():
        logger.error(f"Input PCB not found: {input_pcb}")
        return

    logger.info(f"Parsing PCB: {input_pcb}")
    parse_result = parse_kicad_pcb(input_pcb)
    board = parse_result.board
    netlist = parse_result.netlist
    
    # Configure pipeline
    config = PipelineConfig(
        resolution_mm=0.2,
        fine_resolution_mm=0.1,  # Use 0.1mm for full board to be safe but reasonably fast
        enable_smoothing=True,
        enable_dithering=False,
        via_cost=50.0
    )
    
    pipeline = CSpaceRoutingPipeline(board, netlist, config)
    logger.info("Extracting geometry and initializing C-Space...")
    pipeline.extract_geometry()
    pipeline.initialize_router()
    
    # Order nets
    loops = LoopCollection() # Could load from YAML if needed
    net_order = order_nets(netlist, loops)
    
    # Exclude power planes (will be handled by zone filling)
    POWER_NETS = ["GND", "PGND", "+340V_BUS", "DC_BUS_RTN", "AC_L", "AC_N"]
    net_order = [n for n in net_order if n not in POWER_NETS]
    
    logger.info(f"Starting routing for {len(net_order)} nets...")
    start_time = time.time()
    result = pipeline.route_all(net_order)
    elapsed = time.time() - start_time
    
    logger.info(f"Routing completed in {elapsed:.1f}s")
    logger.info(f"Completion: {result.successful_count}/{len(net_order)} ({result.completion_rate:.1f}%)")
    
    if result.failed_count > 0:
        logger.warning(f"Failed nets: {result.failed_count}")
        # for name, res in result.net_results.items():
        #     if not res.success:
        #         logger.warning(f"  {name}: {res.failure_reason}")

    # Write output
    logger.info(f"Writing traces to {output_pcb}")
    
    # 1. Update component positions in output if they shifted (they shouldn't here)
    placements = {
        c.ref: PlacementUpdate(
            ref=c.ref,
            x=c.initial_position[0] + board.origin[0],
            y=c.initial_position[1] + board.origin[1],
            rotation=c.initial_rotation * 90.0 if c.initial_rotation is not None else 0.0
        ) for c in netlist.components if c.initial_position
    }
    
    # Write traces
    import jax.numpy as jnp
    positions = jnp.array([c.initial_position for c in netlist.components])
    
    # We use write_traces_to_pcb from io.trace_writer
    # Note: result.net_results is a dict of RoutePath
    items_added = write_traces_to_pcb(
        input_pcb,
        output_pcb,
        result.net_results,
        cell_size=config.resolution_mm, # This might be tricky if multi-res used
        origin=board.origin,
        netlist=netlist,
        component_positions=positions
    )
    
    logger.info(f"Successfully added {items_added} trace segments and vias.")
    logger.info("Validation run complete.")

if __name__ == "__main__":
    run_full_validation()
