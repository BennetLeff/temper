"""
Lightweight Routability Analysis for Benders Integration.

This module provides fast routability checking specifically designed
for the Benders decomposition loop. It skips expensive operations
(full skeleton extraction, topology solving, A* pathfinding) that
are not needed for capacity-based feasibility analysis.

Typical runtime: 2-5 seconds (vs 60+ seconds for full pipeline)
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
from temper_placer.router_v6.stage0_data import ParsedPCB, DesignRules
from temper_placer.router_v6.routing_space import compute_routing_space
from temper_placer.router_v6.channel_skeleton_fast import (
    extract_channel_skeleton_fast,
    extract_channel_capacities_direct,
    FastChannelSkeleton,
)


@dataclass
class BendersRoutabilityResult:
    """Result of lightweight routability analysis."""
    
    is_feasible: bool
    total_capacity: float  # Estimated routing capacity
    utilization: float  # Demand / capacity ratio
    bottleneck_layer: str | None
    bottleneck_info: dict
    
    # Timing
    parse_time_sec: float
    routing_space_time_sec: float
    analysis_time_sec: float
    total_time_sec: float
    
    # Data for cut generation
    skeletons: dict[str, FastChannelSkeleton]
    capacities: dict[str, dict]
    design_rules: DesignRules


def check_routability_fast(
    pcb_file: Path | str,
    verbose: bool = False,
) -> BendersRoutabilityResult:
    """
    Fast routability check for Benders integration.
    
    This runs only the stages needed for capacity-based feasibility:
    - Stage 0: Parse PCB
    - Stage 2a: Compute routing space
    - Fast capacity estimation
    
    Skips:
    - Stage 1: Escape vias (not needed)
    - Full skeleton extraction (too slow)
    - Stage 3: Topology solver (not needed)
    - Stage 4: Geometric realization (not needed)
    
    Args:
        pcb_file: Path to KiCad PCB file
        verbose: Print progress
        
    Returns:
        BendersRoutabilityResult with feasibility info
    """
    pcb_file = Path(pcb_file)
    total_start = time.time()
    
    # Stage 0: Parse PCB
    if verbose:
        print("  [Benders] Parsing PCB...", end=" ", flush=True)
    parse_start = time.time()
    pcb = parse_kicad_pcb_v6(pcb_file)
    parse_time = time.time() - parse_start
    if verbose:
        print(f"{parse_time:.2f}s", flush=True)
    
    # Stage 2a: Compute routing space
    if verbose:
        print("  [Benders] Computing routing space...", end=" ", flush=True)
    rs_start = time.time()
    routing_spaces = compute_routing_space(pcb, escape_vias=None)
    rs_time = time.time() - rs_start
    if verbose:
        print(f"{rs_time:.2f}s", flush=True)
    
    # Fast capacity estimation
    if verbose:
        print("  [Benders] Estimating capacities...", end=" ", flush=True)
    analysis_start = time.time()
    
    skeletons = {}
    capacities = {}
    total_capacity = 0.0
    bottleneck_layer = None
    min_capacity_ratio = float('inf')
    
    for layer_name, rs in routing_spaces.items():
        # Use fast skeleton (grid-based)
        skeletons[layer_name] = extract_channel_skeleton_fast(
            rs,
            grid_spacing=5.0,  # 5mm grid for speed
            min_polygon_area=10.0,
        )
        
        # Direct capacity estimation
        capacities[layer_name] = extract_channel_capacities_direct(
            rs,
            pcb.design_rules,
        )
        
        layer_capacity = capacities[layer_name]["capacity_traces"]
        total_capacity += layer_capacity
        
        # Track bottleneck
        if layer_capacity < min_capacity_ratio:
            min_capacity_ratio = layer_capacity
            bottleneck_layer = layer_name
    
    analysis_time = time.time() - analysis_start
    if verbose:
        print(f"{analysis_time:.2f}s", flush=True)
    
    # Estimate demand (number of nets * avg pins per net)
    num_nets = len(pcb.nets)
    avg_pins = sum(len(n.pins) for n in pcb.nets) / max(num_nets, 1)
    estimated_demand = num_nets * (avg_pins - 1)  # Rough: each net needs (pins-1) connections
    
    # Feasibility heuristic
    utilization = estimated_demand / max(total_capacity, 1)
    is_feasible = utilization < 0.8  # 80% utilization threshold
    
    total_time = time.time() - total_start
    
    if verbose:
        print(f"  [Benders] Total: {total_time:.2f}s, Feasible: {is_feasible}", flush=True)
    
    return BendersRoutabilityResult(
        is_feasible=is_feasible,
        total_capacity=total_capacity,
        utilization=utilization,
        bottleneck_layer=bottleneck_layer,
        bottleneck_info={
            "layer": bottleneck_layer,
            "capacity": min_capacity_ratio,
            "demand": estimated_demand,
        },
        parse_time_sec=parse_time,
        routing_space_time_sec=rs_time,
        analysis_time_sec=analysis_time,
        total_time_sec=total_time,
        skeletons=skeletons,
        capacities=capacities,
        design_rules=pcb.design_rules,
    )


def update_pcb_positions_fast(
    pcb_file: Path | str,
    positions: dict[str, tuple[float, float]],
    output_file: Path | str | None = None,
) -> Path:
    """
    Update component positions in PCB file (fast version).
    
    Args:
        pcb_file: Source PCB file
        positions: New positions {ref: (x, y)}
        output_file: Output file (defaults to overwriting source)
        
    Returns:
        Path to updated file
    """
    pcb_file = Path(pcb_file)
    output_file = Path(output_file) if output_file else pcb_file
    
    from kiutils.board import Board
    
    board = Board.from_file(str(pcb_file))
    
    updated = 0
    for fp in board.footprints:
        ref = fp.entryName
        if ref in positions:
            x, y = positions[ref]
            fp.position.X = x
            fp.position.Y = y
            updated += 1
    
    board.to_file(str(output_file))
    return output_file
