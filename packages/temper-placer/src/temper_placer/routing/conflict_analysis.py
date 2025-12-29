"""
Conflict analysis for maze routing (temper-wna.6).

This module provides tools to analyze and classify routing conflicts,
enabling better diagnostics and targeted fixes.

Conflict Types:
- OVERLAP: Two nets share the same cell (most common)
- BOTTLENECK: 3+ nets share a cell (severe congestion)
- ESCAPE: Conflict occurs at pin escape point
- BOUNDARY: Conflict at board edge or keepout boundary
"""

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

import jax.numpy as jnp
from jax import Array

if TYPE_CHECKING:
    from temper_placer.routing.maze_router import MazeRouter


class ConflictType(Enum):
    """Classification of routing conflicts."""
    OVERLAP = "overlap"           # 2 nets in same cell
    BOTTLENECK = "bottleneck"     # 3+ nets in same cell
    ESCAPE = "escape"             # conflict at pin escape
    BOUNDARY = "boundary"         # conflict near board edge


@dataclass
class ConflictInfo:
    """Detailed information about a routing conflict."""
    cell: tuple[int, int, int]  # (x, y, layer)
    nets: list[str]             # nets sharing this cell
    conflict_type: ConflictType
    severity: float             # 0.0-1.0 (higher = worse)
    location_mm: tuple[float, float] | None = None  # world coordinates


@dataclass 
class ConflictAnalysis:
    """Aggregate conflict analysis results."""
    total_conflicts: int
    overlap_count: int
    bottleneck_count: int
    escape_count: int
    boundary_count: int
    conflicts: list[ConflictInfo]
    conflicted_nets: list[str]
    worst_cells: list[tuple[int, int, int, int]]  # (x, y, layer, net_count)
    heatmap: Array | None = None


def analyze_conflicts(router: "MazeRouter") -> ConflictAnalysis:
    """Analyze and classify all conflicts in a router state.
    
    Args:
        router: MazeRouter with routing results.
        
    Returns:
        ConflictAnalysis with classified conflicts.
    """
    conflicts: list[ConflictInfo] = []
    conflicted_nets: set[str] = set()
    overlap_count = 0
    bottleneck_count = 0
    escape_count = 0
    boundary_count = 0
    worst_cells: list[tuple[int, int, int, int]] = []
    
    for (x, y, layer), nets in router.net_occupancy.items():
        net_count = len(nets)
        if net_count <= 1:
            continue
            
        conflicted_nets.update(nets)
        
        # Classify conflict type
        if net_count == 2:
            conflict_type = ConflictType.OVERLAP
            overlap_count += 1
            severity = 0.3
        else:
            conflict_type = ConflictType.BOTTLENECK
            bottleneck_count += 1
            severity = min(1.0, 0.3 + 0.2 * (net_count - 2))
        
        # Check for boundary conflicts
        if (x <= 2 or x >= router.grid_size[0] - 3 or 
            y <= 2 or y >= router.grid_size[1] - 3):
            conflict_type = ConflictType.BOUNDARY
            boundary_count += 1
            severity = min(1.0, severity + 0.2)
        
        # Convert to world coordinates
        loc_mm = (
            x * router.cell_size + router.origin[0],
            y * router.cell_size + router.origin[1]
        )
        
        conflicts.append(ConflictInfo(
            cell=(x, y, layer),
            nets=sorted(nets),
            conflict_type=conflict_type,
            severity=severity,
            location_mm=loc_mm,
        ))
        
        worst_cells.append((x, y, layer, net_count))
    
    # Sort worst cells by net count
    worst_cells.sort(key=lambda c: -c[3])
    
    return ConflictAnalysis(
        total_conflicts=len(conflicts),
        overlap_count=overlap_count,
        bottleneck_count=bottleneck_count,
        escape_count=escape_count,
        boundary_count=boundary_count,
        conflicts=conflicts,
        conflicted_nets=sorted(conflicted_nets),
        worst_cells=worst_cells[:10],  # Top 10 worst
    )


def get_conflict_heatmap(router: "MazeRouter") -> Array:
    """Generate a conflict heatmap showing severity per cell.
    
    Args:
        router: MazeRouter with routing results.
        
    Returns:
        (W, H, L) array with conflict severity per cell.
        0 = no conflict, higher = more nets sharing cell.
    """
    heatmap = jnp.zeros(
        (router.grid_size[0], router.grid_size[1], router.num_layers),
        dtype=jnp.float32
    )
    
    for (x, y, layer), nets in router.net_occupancy.items():
        if len(nets) > 1:
            # Severity = number of extra nets (beyond 1)
            heatmap = heatmap.at[x, y, layer].set(float(len(nets) - 1))
    
    return heatmap


def identify_bottleneck_regions(
    router: "MazeRouter",
    threshold: int = 3,
    min_region_size: int = 4,
) -> list[tuple[int, int, int, int, int]]:
    """Find regions with high conflict density.
    
    Args:
        router: MazeRouter with routing results.
        threshold: Minimum nets-per-cell to consider congested.
        min_region_size: Minimum cells to form a region.
        
    Returns:
        List of (x_min, y_min, x_max, y_max, layer) bounding boxes.
    """
    congested_cells: list[tuple[int, int, int]] = []
    
    for (x, y, layer), nets in router.net_occupancy.items():
        if len(nets) >= threshold:
            congested_cells.append((x, y, layer))
    
    if len(congested_cells) < min_region_size:
        return []
    
    # Simple bounding box for now (could be improved with clustering)
    regions: list[tuple[int, int, int, int, int]] = []
    
    for layer in range(router.num_layers):
        layer_cells = [(x, y) for (x, y, l) in congested_cells if l == layer]
        if len(layer_cells) >= min_region_size:
            xs = [c[0] for c in layer_cells]
            ys = [c[1] for c in layer_cells]
            regions.append((min(xs), min(ys), max(xs), max(ys), layer))
    
    return regions


def format_conflict_report(analysis: ConflictAnalysis) -> str:
    """Generate a human-readable conflict report.
    
    Args:
        analysis: ConflictAnalysis results.
        
    Returns:
        Formatted report string.
    """
    lines = [
        "=" * 50,
        "ROUTING CONFLICT ANALYSIS",
        "=" * 50,
        "",
        f"Total Conflicts: {analysis.total_conflicts}",
        f"  - Overlap (2 nets):     {analysis.overlap_count}",
        f"  - Bottleneck (3+ nets): {analysis.bottleneck_count}",
        f"  - Boundary conflicts:   {analysis.boundary_count}",
        "",
        f"Conflicted Nets ({len(analysis.conflicted_nets)}):",
    ]
    
    if len(analysis.conflicted_nets) <= 10:
        for net in analysis.conflicted_nets:
            lines.append(f"  - {net}")
    else:
        for net in analysis.conflicted_nets[:5]:
            lines.append(f"  - {net}")
        lines.append(f"  ... and {len(analysis.conflicted_nets) - 5} more")
    
    if analysis.worst_cells:
        lines.append("")
        lines.append("Worst Congestion Points:")
        for x, y, layer, count in analysis.worst_cells[:5]:
            lines.append(f"  - Cell ({x}, {y}) L{layer+1}: {count} nets")
    
    lines.append("")
    lines.append("=" * 50)
    
    return "\n".join(lines)
