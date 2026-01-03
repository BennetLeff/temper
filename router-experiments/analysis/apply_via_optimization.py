#!/usr/bin/env python3
"""
Apply Via Optimization Pass to a routed KiCad PCB.

This script:
1. Parses an existing routed PCB.
2. Converts geometry to internal PCBGeometry representation.
3. Runs ViaOptimizer (Consolidation -> Reposition -> Elimination).
4. Exports the optimized geometry back to a new KiCad PCB.
"""

import sys
import os
from pathlib import Path
import logging

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root / "packages/temper-placer/src"))

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.kicad_exporter import export_from_geometry
from temper_placer.routing.constraints.spatial_index import PCBGeometry, Track, Via, Pad
from temper_placer.routing.constraints.geometry import Point
from temper_placer.routing.constraints.drc_oracle import DRCOracle
from temper_placer.routing.constraints.design_rules import ClearanceMatrix
from temper_placer.routing.post_processing.via_optimizer import ViaOptimizer

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Map KiCad layers to numeric indices
LAYER_MAP = {
    "F.Cu": 0,
    "B.Cu": 1,
    "In1.Cu": 2,
    "In2.Cu": 3,
}

def apply_optimization(input_pcb: str, output_pcb: str):
    input_path = Path(input_pcb)
    output_path = Path(output_pcb)
    
    if not input_path.exists():
        logger.error(f"Input PCB not found: {input_pcb}")
        return

    logger.info(f"Loading PCB: {input_pcb}")
    parse_result = parse_kicad_pcb(input_path)
    
    # 1. Convert to PCBGeometry
    geometry = PCBGeometry()
    
    # Add Pads
    for p in parse_result.pads:
        layer_idx = LAYER_MAP.get(p.layer, 0)
        geometry.add_pad(Pad(
            center=Point(p.position[0], p.position[1]),
            shape=p.shape,
            size=p.size,
            net=p.net or "<no net>",
            layer=layer_idx,
            rotation=p.rotation,
        ))
    
    # Add Tracks
    for t in parse_result.traces:
        layer_idx = LAYER_MAP.get(t.layer, 0)
        geometry.add_track(Track(
            start=Point(t.start[0], t.start[1]),
            end=Point(t.end[0], t.end[1]),
            width=t.width,
            net=t.net or "<no net>",
            layer=layer_idx,
        ))
        
    # Add Vias
    for v in parse_result.vias:
        geometry.add_via(Via(
            center=Point(v.position[0], v.position[1]),
            diameter=v.diameter,
            drill=v.drill,
            net=v.net or "<no net>",
        ))
        
    geometry.rebuild_index()
    logger.info(f"Geometry initialized: {len(geometry.tracks)} tracks, {len(geometry.vias)} vias, {len(geometry.pads)} pads")
    
    # 2. Setup DRCOracle and Optimizer
    # Use default rules (0.2mm clearance)
    rules = ClearanceMatrix(default_clearance=0.2)
    oracle = DRCOracle(rules=rules, geometry=geometry)
    
    # Increase consolidation radius to be even more aggressive
    optimizer = ViaOptimizer(
        oracle=oracle,
        consolidation_radius=1.5,  # mm (was 1.0)
        min_clearance=0.2,
        max_iterations=20  # (was 10)
    )
    
    # 3. Run Optimization
    logger.info("Running via optimization pass...")
    optimized_geom = optimizer.optimize_vias(geometry)
    
    stats = optimizer.stats
    logger.info(f"Optimization complete:")
    logger.info(f"  Vias consolidated: {stats.vias_consolidated}")
    logger.info(f"  Vias repositioned: {stats.vias_repositioned}")
    logger.info(f"  Vias eliminated:   {stats.vias_eliminated}")
    logger.info(f"  Violations fixed:  {stats.violations_fixed}")
    
    # 4. Export
    logger.info(f"Exporting optimized PCB to: {output_pcb}")
    export_from_geometry(
        template_pcb=input_path,
        output_pcb=output_path,
        tracks=optimized_geom.tracks,
        vias=optimized_geom.vias,
    )
    logger.info("Done!")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 apply_via_optimization.py <input.kicad_pcb> <output.kicad_pcb>")
        sys.exit(1)
    
    apply_optimization(sys.argv[1], sys.argv[2])
