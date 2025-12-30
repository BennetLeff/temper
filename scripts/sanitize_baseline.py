#!/usr/bin/env python3
"""
Sanitize baseline PCB by removing DRC-violating pre-routed tracks.

This script:
1. Loads a pre-routed PCB file
2. Identifies tracks/vias on specified nets that cause DRC violations
3. Removes the violating geometry
4. Saves a clean baseline for routing

Usage:
    python sanitize_baseline.py pre_routed_v5.kicad_pcb -o pre_routed_v6.kicad_pcb
"""

import argparse
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from kiutils.board import Board
from rich.console import Console
from rich.table import Table

console = Console()


@dataclass
class SanitizationResult:
    """Result of sanitization operation."""
    tracks_removed: int = 0
    vias_removed: int = 0
    nets_affected: list[str] = None
    violations_before: int = 0
    violations_after: int = 0
    
    def __post_init__(self):
        if self.nets_affected is None:
            self.nets_affected = []


def build_net_map(board: Board) -> dict[int, str]:
    """Build mapping from net ID to net name."""
    net_map = {}
    for net in board.nets:
        net_map[net.number] = net.name
    return net_map


def resolve_net_name(net_obj, net_map: dict[int, str]) -> str:
    """Resolve net name from net object (may be int or object with number/name)."""
    if isinstance(net_obj, int):
        return net_map.get(net_obj, "")
    if hasattr(net_obj, 'name') and net_obj.name:
        return net_obj.name
    if hasattr(net_obj, 'number'):
        return net_map.get(net_obj.number, "")
    return ""


def get_pad_geometries(board: Board, net_map: dict[int, str]) -> dict[str, list[tuple[float, float, float, float]]]:
    """Extract pad bounding boxes keyed by net name.
    
    Returns:
        Dict mapping net_name -> list of (x, y, half_width, half_height)
    """
    pads_by_net = {}
    
    for fp in board.footprints:
        fp_x = fp.position.X
        fp_y = fp.position.Y
        
        for pad in fp.pads:
            net_name = resolve_net_name(pad.net, net_map)
            if not net_name:
                continue
                
            abs_x = fp_x + pad.position.X
            abs_y = fp_y + pad.position.Y
            half_w = pad.size.X / 2
            half_h = pad.size.Y / 2
            
            if net_name not in pads_by_net:
                pads_by_net[net_name] = []
            pads_by_net[net_name].append((abs_x, abs_y, half_w, half_h))
    
    return pads_by_net


def point_to_segment_distance(px, py, x1, y1, x2, y2) -> float:
    """Calculate minimum distance from point (px,py) to line segment (x1,y1)-(x2,y2)."""
    dx = x2 - x1
    dy = y2 - y1
    
    if dx == 0 and dy == 0:
        # Degenerate segment (point)
        return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
    
    # Parameter t for projection of point onto line
    t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    
    # Closest point on segment
    closest_x = x1 + t * dx
    closest_y = y1 + t * dy
    
    return ((px - closest_x) ** 2 + (py - closest_y) ** 2) ** 0.5


def segment_to_rect_distance(x1, y1, x2, y2, rect_cx, rect_cy, half_w, half_h) -> float:
    """Calculate minimum distance from line segment to axis-aligned rectangle.
    
    Returns 0 if segment intersects or is inside the rectangle.
    """
    # Check if any endpoint is inside the rectangle
    def point_in_rect(px, py):
        return abs(px - rect_cx) <= half_w and abs(py - rect_cy) <= half_h
    
    if point_in_rect(x1, y1) or point_in_rect(x2, y2):
        return 0.0
    
    # Check if segment crosses rectangle (line-rectangle intersection)
    # For simplicity, we'll check distance to all 4 corners and 4 edges
    
    # Rectangle corners
    corners = [
        (rect_cx - half_w, rect_cy - half_h),
        (rect_cx + half_w, rect_cy - half_h),
        (rect_cx + half_w, rect_cy + half_h),
        (rect_cx - half_w, rect_cy + half_h),
    ]
    
    # Minimum distance from segment to corners
    min_dist = float('inf')
    for cx, cy in corners:
        d = point_to_segment_distance(cx, cy, x1, y1, x2, y2)
        min_dist = min(min_dist, d)
    
    # Also check distance from segment endpoints to rectangle edges
    # Distance from point to rectangle boundary
    for px, py in [(x1, y1), (x2, y2)]:
        # Distance to nearest edge
        dx = max(0, abs(px - rect_cx) - half_w)
        dy = max(0, abs(py - rect_cy) - half_h)
        d = (dx * dx + dy * dy) ** 0.5
        min_dist = min(min_dist, d)
    
    return min_dist


def segment_violates_pad(seg, pad_x, pad_y, pad_hw, pad_hh, clearance=0.2, track_width=0.25) -> bool:
    """Check if a segment violates clearance from a pad.
    
    Takes into account both the track width and required clearance.
    """
    x1, y1 = seg.start.X, seg.start.Y
    x2, y2 = seg.end.X, seg.end.Y
    
    # Effective clearance = required clearance + half track width
    eff_clearance = clearance + track_width / 2
    
    # Get distance from segment to pad rectangle
    dist = segment_to_rect_distance(x1, y1, x2, y2, pad_x, pad_y, pad_hw, pad_hh)
    
    return dist < eff_clearance


def find_violating_tracks(board: Board, target_nets: list[str], clearance: float = 0.2, net_map: dict[int, str] = None) -> list:
    """Find tracks on target_nets that cross pads of OTHER nets.
    
    Args:
        board: KiCad board
        target_nets: Nets to check for violations
        clearance: DRC clearance in mm
        net_map: Mapping from net ID to net name
        
    Returns:
        List of (track_index, track, violation_description)
    """
    if net_map is None:
        net_map = build_net_map(board)
    pads_by_net = get_pad_geometries(board, net_map)
    violations = []
    
    for idx, item in enumerate(board.traceItems):
        # Only check segments (not vias, arcs, etc.)
        if not (hasattr(item, 'start') and hasattr(item, 'end')):
            continue
            
        track_net = resolve_net_name(item.net, net_map)
        if track_net not in target_nets:
            continue
        
        # Check against pads of OTHER nets
        for other_net, pads in pads_by_net.items():
            if other_net == track_net:
                continue  # Same net, no violation
                
            for (pad_x, pad_y, pad_hw, pad_hh) in pads:
                track_width = getattr(item, 'width', 0.25)
                if segment_violates_pad(item, pad_x, pad_y, pad_hw, pad_hh, clearance, track_width):
                    violations.append((
                        idx,
                        item,
                        f"{track_net} track crosses {other_net} pad at ({pad_x:.2f}, {pad_y:.2f})"
                    ))
                    break  # One violation is enough to flag this track
    
    return violations


def find_violating_vias(board: Board, target_nets: list[str], clearance: float = 0.2, net_map: dict[int, str] = None) -> list:
    """Find vias on target_nets that are too close to pads of OTHER nets."""
    if net_map is None:
        net_map = build_net_map(board)
    pads_by_net = get_pad_geometries(board, net_map)
    violations = []
    
    for idx, item in enumerate(board.traceItems):
        # Check vias
        if not (hasattr(item, 'position') and hasattr(item, 'drill')):
            continue
            
        via_net = resolve_net_name(item.net, net_map)
        if via_net not in target_nets:
            continue
        
        via_x = item.position.X
        via_y = item.position.Y
        via_radius = item.size / 2
        
        for other_net, pads in pads_by_net.items():
            if other_net == via_net:
                continue
                
            for (pad_x, pad_y, pad_hw, pad_hh) in pads:
                # Simple distance check
                dx = abs(via_x - pad_x)
                dy = abs(via_y - pad_y)
                eff_clearance = via_radius + clearance
                
                if dx < (pad_hw + eff_clearance) and dy < (pad_hh + eff_clearance):
                    violations.append((
                        idx,
                        item,
                        f"{via_net} via at ({via_x:.2f}, {via_y:.2f}) too close to {other_net} pad"
                    ))
                    break
    
    return violations


def sanitize_board(
    board: Board,
    target_nets: list[str],
    clearance: float = 0.2,
    dry_run: bool = False
) -> SanitizationResult:
    """Remove tracks/vias on target_nets that violate DRC.
    
    Args:
        board: KiCad board (modified in place)
        target_nets: Nets to sanitize
        clearance: DRC clearance in mm
        dry_run: If True, don't actually remove anything
        
    Returns:
        SanitizationResult
    """
    result = SanitizationResult()
    
    # Build net map for consistent net name resolution
    net_map = build_net_map(board)
    
    # Find violations
    track_violations = find_violating_tracks(board, target_nets, clearance, net_map)
    via_violations = find_violating_vias(board, target_nets, clearance, net_map)
    
    result.violations_before = len(track_violations) + len(via_violations)
    
    if dry_run:
        console.print(f"\n[yellow]DRY RUN - Would remove:[/]")
        for idx, item, desc in track_violations:
            console.print(f"  - Track: {desc}")
        for idx, item, desc in via_violations:
            console.print(f"  - Via: {desc}")
        return result
    
    # Collect indices to remove (in reverse order to preserve indices)
    indices_to_remove = set()
    
    for idx, item, desc in track_violations:
        indices_to_remove.add(idx)
        result.tracks_removed += 1
        net = item.net.name if item.net and hasattr(item.net, 'name') else ""
        if net and net not in result.nets_affected:
            result.nets_affected.append(net)
        console.print(f"  [red]Removing:[/] {desc}")
    
    for idx, item, desc in via_violations:
        indices_to_remove.add(idx)
        result.vias_removed += 1
        net = item.net.name if item.net and hasattr(item.net, 'name') else ""
        if net and net not in result.nets_affected:
            result.nets_affected.append(net)
        console.print(f"  [red]Removing:[/] {desc}")
    
    # Remove in reverse order
    for idx in sorted(indices_to_remove, reverse=True):
        del board.traceItems[idx]
    
    result.violations_after = 0  # We removed all detected violations
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Sanitize pre-routed PCB by removing DRC-violating tracks"
    )
    parser.add_argument("input_pcb", type=Path, help="Input PCB file")
    parser.add_argument("-o", "--output", type=Path, help="Output PCB file")
    parser.add_argument(
        "--nets", 
        nargs="+", 
        default=["AC_L", "AC_N", "DC_BUS+", "DC_BUS-"],
        help="Nets to check for violations (default: AC_L AC_N DC_BUS+ DC_BUS-)"
    )
    parser.add_argument(
        "--clearance",
        type=float,
        default=0.2,
        help="DRC clearance in mm (default: 0.2)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually remove anything, just report"
    )
    parser.add_argument(
        "--all-nets",
        action="store_true",
        help="Check ALL nets for pad-crossing violations (not just specified nets)"
    )
    
    args = parser.parse_args()
    
    if not args.output:
        stem = args.input_pcb.stem
        # Increment version number if present
        if stem.endswith("_v5"):
            stem = stem[:-1] + "6"
        elif stem.endswith("_v6"):
            stem = stem[:-1] + "7"
        else:
            stem = stem + "_sanitized"
        args.output = args.input_pcb.with_name(stem + args.input_pcb.suffix)
    
    console.print(f"[bold blue]PCB Baseline Sanitizer[/]")
    console.print(f"Input: {args.input_pcb}")
    console.print(f"Output: {args.output}")
    console.print(f"Target nets: {args.nets}")
    console.print(f"Clearance: {args.clearance}mm")
    
    # Load board
    console.print("\n[cyan]Loading PCB...[/]")
    try:
        board = Board.from_file(str(args.input_pcb))
    except Exception as e:
        console.print(f"[red]Error loading PCB: {e}[/]")
        sys.exit(1)
    
    # Get all nets if requested
    if args.all_nets:
        all_nets = set()
        for item in board.traceItems:
            if hasattr(item, 'net') and item.net and hasattr(item.net, 'name'):
                all_nets.add(item.net.name)
        args.nets = list(all_nets)
        console.print(f"[yellow]Checking ALL {len(args.nets)} nets[/]")
    
    # Sanitize
    console.print("\n[cyan]Scanning for violations...[/]")
    result = sanitize_board(board, args.nets, args.clearance, args.dry_run)
    
    # Summary
    console.print("\n[bold]Summary:[/]")
    table = Table()
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Violations found", str(result.violations_before))
    table.add_row("Tracks removed", str(result.tracks_removed))
    table.add_row("Vias removed", str(result.vias_removed))
    table.add_row("Nets affected", ", ".join(result.nets_affected) if result.nets_affected else "none")
    console.print(table)
    
    if args.dry_run:
        console.print("\n[yellow]Dry run complete. No changes written.[/]")
        return
    
    if result.tracks_removed == 0 and result.vias_removed == 0:
        console.print("\n[green]No violations found! File is clean.[/]")
        return
    
    # Save
    console.print(f"\n[cyan]Saving to {args.output}...[/]")
    try:
        board.to_file(str(args.output))
        console.print(f"[bold green]✓ Saved sanitized PCB[/]")
    except Exception as e:
        console.print(f"[red]Error saving PCB: {e}[/]")
        sys.exit(1)
    
    console.print("\n[bold yellow]Note:[/] The following nets may need re-routing:")
    for net in result.nets_affected:
        console.print(f"  - {net}")


if __name__ == "__main__":
    main()
