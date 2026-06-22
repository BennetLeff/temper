"""info command for temper-placer CLI."""

from __future__ import annotations

import click
import sys
from pathlib import Path
from ._io import console
from ._io import Table

@click.command()
@click.argument("input_pcb", type=click.Path(exists=True, path_type=Path))
def info(input_pcb: Path) -> None:
    """
    Display information about a KiCad PCB file.

    Shows component count, net count, board dimensions, etc.

    Example:
        temper-placer info temper.kicad_pcb
    """
    console.print(f"[bold blue]PCB Info:[/] {input_pcb}")

    try:
        from temper_placer.io.kicad_parser import parse_kicad_pcb

        result = parse_kicad_pcb(input_pcb)
        netlist = result.netlist
        board = result.board

        table = Table(title="PCB Summary")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("File", str(input_pcb))
        table.add_row("Components", str(netlist.n_components))
        table.add_row("Nets", str(netlist.n_nets))

        if board:
            table.add_row("Board Size", f"{board.width:.1f}mm x {board.height:.1f}mm")
            table.add_row("Origin", f"({board.origin[0]:.1f}, {board.origin[1]:.1f})")
            table.add_row("Zones", str(len(board.zones)))
            table.add_row("Mounting Holes", str(len(board.mounting_holes)))

        console.print(table)

        if result.has_warnings:
            console.print("\n[yellow]Warnings:[/]")
            for w in result.warnings:
                console.print(f"  - {w}")

        # Show component breakdown by type
        if netlist.components:
            console.print("\n[bold]Component Types:[/]")
            prefixes: dict = {}
            for c in netlist.components:
                prefix = "".join(c for c in c.ref if not c.isdigit())
                prefixes[prefix] = prefixes.get(prefix, 0) + 1

            for prefix, count in sorted(prefixes.items(), key=lambda x: -x[1]):
                console.print(f"  {prefix}: {count}")

    except Exception as e:
        console.print(f"[red]Failed to parse PCB: {e}[/]")
        sys.exit(1)
