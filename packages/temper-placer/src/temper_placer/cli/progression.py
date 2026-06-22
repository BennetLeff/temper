"""progression command for temper-placer CLI."""

from __future__ import annotations

import click
import sys
from pathlib import Path
from ._io import console

@click.command()
@click.argument("history_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--pcb",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Reference PCB file to get board dimensions and component info.",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="Output HTML file path.",
)
def progression(
    history_file: Path,
    pcb: Path,
    output: Path | None,
) -> None:
    """
    Visualize placement evolution from history file.

    Generates an interactive HTML visualization of how component positions
    changed during optimization.
    """
    console.print(f"[bold blue]Visualizing Progression:[/] {history_file}")

    try:
        from temper_placer.io.kicad_parser import parse_kicad_pcb
        from temper_placer.visualization.progression import render_progression_html

        # 1. Get PCB info
        result = parse_kicad_pcb(pcb)
        netlist = result.netlist
        board = result.board

        pcb_info = {
            "width": board.width,
            "height": board.height,
            "refs": [c.ref for c in netlist.components],
            "widths": [c.width for c in netlist.components],
            "heights": [c.height for c in netlist.components],
        }

        # 2. Render HTML
        html_content = render_progression_html(history_file, pcb_info)

        # 3. Save or open
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(html_content)
            console.print(f"[green]✓[/] Wrote {output}")
        else:
            import tempfile
            import webbrowser

            with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
                f.write(html_content)
                temp_path = f.name

            console.print("[green]✓[/] Opening in browser...")
            webbrowser.open(f"file://{temp_path}")

    except Exception as e:
        console.print(f"[red]Failed: {e}[/]")
        sys.exit(1)
