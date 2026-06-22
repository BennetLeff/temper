"""Internal IO utilities for the CLI (console, summaries, rich setup)."""
from __future__ import annotations
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table

console = Console()

def _print_placement_summary(console_obj, netlist, state, constraints, min_separation=2.0):
    import numpy as np
    from rich.table import Table as RT
    positions = np.array(state.positions)
    n = len(netlist.components)
    if n == 0:
        return
    widths = np.array([c.bounds[0] for c in netlist.components])
    heights = np.array([c.bounds[1] for c in netlist.components])
    overlap_pairs = []
    for i in range(n):
        hw_i, hh_i = widths[i] / 2, heights[i] / 2
        for j in range(i + 1, n):
            hw_j, hh_j = widths[j] / 2, heights[j] / 2
            dx = abs(positions[i, 0] - positions[j, 0])
            dy = abs(positions[i, 1] - positions[j, 1])
            overlap_x = (hw_i + hw_j + min_separation) - dx
            overlap_y = (hh_i + hh_j + min_separation) - dy
            if overlap_x > 0 and overlap_y > 0:
                overlap_pairs.append((netlist.components[i].ref, netlist.components[j].ref, min(overlap_x, overlap_y)))
    console_obj.print("\n[bold cyan]--- Placement Summary ---")
    fixed_count = sum(1 for c in netlist.components if c.fixed)
    console_obj.print(f"  Components: {n} total, {fixed_count} fixed, {n - fixed_count} optimized")
    if overlap_pairs:
        console_obj.print(f"  [red]Overlaps: {len(overlap_pairs)} pairs[/]")
        for ref_a, ref_b, amount in overlap_pairs[:5]:
            console_obj.print(f"    [red]- {ref_a} <-> {ref_b}: {amount:.1f}mm[/]")
    else:
        console_obj.print(f"  [green]Overlaps: 0 pairs[/]")
    table = RT(title="Component Positions", show_lines=False)
    table.add_column("Ref", style="cyan", width=12)
    table.add_column("Size (mm)", width=10)
    table.add_column("Position", width=14)
    sorted_indices = sorted(range(n), key=lambda i: widths[i] * heights[i], reverse=True)
    for idx in sorted_indices[:15]:
        comp = netlist.components[idx]
        w, h = widths[idx], heights[idx]
        x, y = positions[idx]
        table.add_row(comp.ref, f"{w:.1f}x{h:.1f}", f"({x:.1f}, {y:.1f})")
    console_obj.print(table)
