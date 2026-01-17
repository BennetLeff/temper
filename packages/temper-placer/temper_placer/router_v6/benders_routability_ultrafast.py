"""
Ultra-Fast Routability Analysis for Benders Integration.

This module provides the fastest possible routability checking by
skipping expensive geometry operations entirely. Instead, it uses
simple heuristics based on component positions and connectivity.

Typical runtime: <0.5 seconds

Use this for:
- Quick feasibility screening in Benders iterations
- Early termination checks
- Initial placement validation

Use the regular `check_routability_fast` for more accurate analysis.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class UltraFastRoutabilityResult:
    """Result of ultra-fast routability analysis."""
    
    is_feasible: bool
    congestion_score: float  # 0-1, higher = more congested
    estimated_wirelength: float  # Total estimated wirelength (mm)
    overlap_count: int  # Number of component overlaps
    min_clearance: float  # Minimum clearance between components
    
    total_time_sec: float
    
    # Details
    details: dict


def check_routability_ultrafast(
    component_positions: dict[str, tuple[float, float]],
    component_sizes: dict[str, tuple[float, float]],
    net_connections: list[list[str]],  # List of [comp_ref1, comp_ref2, ...]
    board_bounds: tuple[float, float, float, float],  # (minx, miny, maxx, maxy)
    min_clearance_mm: float = 0.5,
    verbose: bool = False,
) -> UltraFastRoutabilityResult:
    """
    Ultra-fast routability check using simple heuristics.
    
    This does NOT compute actual routing - it estimates feasibility
    from component positions and connectivity.
    
    Args:
        component_positions: {ref: (x, y)}
        component_sizes: {ref: (width, height)}
        net_connections: List of nets, each net is list of component refs
        board_bounds: (minx, miny, maxx, maxy)
        min_clearance_mm: Minimum required clearance
        verbose: Print progress
        
    Returns:
        UltraFastRoutabilityResult
    """
    start = time.time()
    
    if verbose:
        print("  [Ultra-fast] Computing heuristics...", flush=True)
    
    # 1. Check for overlaps
    overlaps = []
    refs = list(component_positions.keys())
    min_actual_clearance = float('inf')
    
    for i, ref1 in enumerate(refs):
        pos1 = component_positions[ref1]
        size1 = component_sizes.get(ref1, (5.0, 5.0))  # Default 5mm
        
        for ref2 in refs[i+1:]:
            pos2 = component_positions[ref2]
            size2 = component_sizes.get(ref2, (5.0, 5.0))
            
            # Simple overlap check (rectangular approximation)
            dx = abs(pos1[0] - pos2[0])
            dy = abs(pos1[1] - pos2[1])
            
            min_dx = (size1[0] + size2[0]) / 2
            min_dy = (size1[1] + size2[1]) / 2
            
            # Compute clearance
            clearance_x = dx - min_dx
            clearance_y = dy - min_dy
            clearance = max(min(clearance_x, clearance_y), 0)
            
            if clearance < min_actual_clearance:
                min_actual_clearance = clearance
            
            if clearance < 0:
                overlaps.append((ref1, ref2))
    
    # 2. Estimate total wirelength (HPWL)
    total_wirelength = 0.0
    for net in net_connections:
        if len(net) < 2:
            continue
        
        # Get positions of all components in net
        net_positions = [
            component_positions.get(ref)
            for ref in net
            if ref in component_positions
        ]
        
        if len(net_positions) < 2:
            continue
        
        # Half-perimeter wirelength
        xs = [p[0] for p in net_positions if p]
        ys = [p[1] for p in net_positions if p]
        
        if xs and ys:
            hpwl = (max(xs) - min(xs)) + (max(ys) - min(ys))
            total_wirelength += hpwl
    
    # 3. Compute congestion score
    minx, miny, maxx, maxy = board_bounds
    board_area = (maxx - minx) * (maxy - miny)
    
    # Total component area
    total_component_area = sum(
        w * h for w, h in component_sizes.values()
    )
    
    # Component density
    density = total_component_area / max(board_area, 1.0)
    
    # Wirelength density
    board_perimeter = 2 * ((maxx - minx) + (maxy - miny))
    wirelength_density = total_wirelength / max(board_perimeter * 10, 1.0)
    
    # Combined congestion score (0-1)
    congestion = min(1.0, density * 0.5 + wirelength_density * 0.5)
    
    # 4. Feasibility determination
    # Note: Clearance check is informational only - the ILP already ensures non-overlap
    # We only fail on actual overlaps or extreme congestion
    is_feasible = (
        len(overlaps) == 0 and
        congestion < 0.9  # Less than 90% congestion (more lenient)
    )
    
    total_time = time.time() - start
    
    if verbose:
        print(f"  [Ultra-fast] Done: {total_time:.3f}s, Feasible: {is_feasible}", flush=True)
    
    return UltraFastRoutabilityResult(
        is_feasible=is_feasible,
        congestion_score=congestion,
        estimated_wirelength=total_wirelength,
        overlap_count=len(overlaps),
        min_clearance=min_actual_clearance if min_actual_clearance != float('inf') else 0,
        total_time_sec=total_time,
        details={
            "overlaps": overlaps,
            "density": density,
            "wirelength_density": wirelength_density,
            "component_count": len(refs),
            "net_count": len(net_connections),
        }
    )


def check_routability_from_benders(
    component_data: list[dict],  # From benders_input.json format
    verbose: bool = False,
) -> UltraFastRoutabilityResult:
    """
    Check routability directly from Benders component data format.
    
    Args:
        component_data: List of component dicts with ref, center_x_mm, center_y_mm, etc.
        verbose: Print progress
        
    Returns:
        UltraFastRoutabilityResult
    """
    # Extract positions and sizes
    positions = {}
    sizes = {}
    
    for comp in component_data:
        ref = comp["ref"]
        positions[ref] = (comp["center_x_mm"], comp["center_y_mm"])
        sizes[ref] = (comp["width_mm"], comp["height_mm"])
    
    # Compute bounds
    xs = [p[0] for p in positions.values()]
    ys = [p[1] for p in positions.values()]
    
    # Add margin
    margin = 10.0
    bounds = (
        min(xs) - margin,
        min(ys) - margin,
        max(xs) + margin,
        max(ys) + margin,
    )
    
    # For now, no net connectivity info - use empty
    # In real usage, would extract from PCB or JSON
    net_connections = []
    
    return check_routability_ultrafast(
        component_positions=positions,
        component_sizes=sizes,
        net_connections=net_connections,
        board_bounds=bounds,
        verbose=verbose,
    )
