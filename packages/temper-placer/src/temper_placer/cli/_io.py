"""Internal IO utilities for the CLI (console, summaries, rich setup)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table

if TYPE_CHECKING:
    pass

console = Console()


def _print_placement_summary(
    console: Console,
    netlist,
    state,
    constraints,
    min_separation: float = 2.0,
) -> None:
    """Print a summary of component placements with overlap detection."""
    import numpy as np
    from rich.table import Table

    positions = np.array(state.positions)
    n = len(netlist.components)

    if n == 0:
        return

    # Compute overlaps
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
                overlap_pairs.append(
                    (
                        netlist.components[i].ref,
                        netlist.components[j].ref,
                        min(overlap_x, overlap_y),
                    )
                )

    console.print("\n[bold cyan]═══ Placement Summary ═══[/]")

    fixed_count = sum(1 for c in netlist.components if c.fixed)
    console.print(f"  Components: {n} total, {fixed_count} fixed, {n - fixed_count} optimized")

    if overlap_pairs:
        console.print(
            f"  [red]Overlaps: {len(overlap_pairs)} pairs (< {min_separation}mm spacing)[/]"
        )
        for ref_a, ref_b, amount in overlap_pairs[:5]:
            console.print(f"    [red]• {ref_a} ↔ {ref_b}: {amount:.1f}mm overlap[/]")
        if len(overlap_pairs) > 5:
            console.print(f"    [dim]... and {len(overlap_pairs) - 5} more[/]")
    else:
        console.print(f"  [green]Overlaps: 0 pairs (✓ {min_separation}mm min spacing)[/]")

    table = Table(title="Component Positions (largest 15)", show_lines=False)
    table.add_column("Ref", style="cyan", width=12)
    table.add_column("Size (mm)", width=10)
    table.add_column("Position", width=14)
    table.add_column("Footprint", style="dim", width=25)

    sorted_indices = sorted(range(n), key=lambda i: widths[i] * heights[i], reverse=True)

    for idx in sorted_indices[:15]:
        comp = netlist.components[idx]
        w, h = widths[idx], heights[idx]
        x, y = positions[idx]
        fp = comp.footprint.split(":")[-1] if ":" in comp.footprint else comp.footprint
        fp = fp[:25] if len(fp) > 25 else fp

        table.add_row(
            comp.ref,
            f"{w:.1f}×{h:.1f}",
            f"({x:.1f}, {y:.1f})",
            fp,
        )

    console.print(table)
