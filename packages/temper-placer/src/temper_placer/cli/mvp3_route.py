"""mvp3-route command for temper-placer CLI."""

from __future__ import annotations

import click
from pathlib import Path
from ._io import console
from ._io import Panel

@click.command("mvp3-route")
@click.argument("input_pcb", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-c",
    "--config",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="YAML configuration file with zones, net classes, and rules.",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    required=True,
    help="Output .kicad_pcb file path.",
)
@click.option(
    "--layers",
    type=int,
    default=4,
    help="Number of routing layers (default: 4).",
)
@click.option(
    "--cell-size",
    type=float,
    default=0.5,
    help="Routing grid cell size in mm (default: 0.5).",
)
@click.option(
    "--slot-spacing",
    type=float,
    default=5.0,
    help="Slot grid spacing for placement in mm (default: 5.0).",
)
def mvp3_route(
    input_pcb: Path,
    config: Path,
    output: Path,
    layers: int,
    cell_size: float,
    slot_spacing: float,
) -> None:
    """
    Run MVP-3 deterministic placement and routing pipeline.
    
    This command uses zone-based placement and layer-aware routing
    to deterministically place and route a KiCad PCB without gradient 
    optimization.
    
    Example:
        temper-placer mvp3-route temper.kicad_pcb \\
            -c temper_config.yaml \\
            -o temper_routed.kicad_pcb \\
            --layers 4
    """
    from temper_placer.pipeline.mvp3_runner import MVP3Config, MVP3Runner
    
    console.print(
        Panel.fit(
            "[bold cyan]MVP-3 Deterministic Pipeline[/]",
            subtitle=f"v{__version__}"
        )
    )
    
    console.print(f"\n[bold]Input:[/] {input_pcb}")
    console.print(f"[bold]Config:[/] {config}")
    console.print(f"[bold]Output:[/] {output}")
    console.print(f"[bold]Layers:[/] {layers}")
    console.print(f"[bold]Grid:[/] {cell_size}mm")
    console.print(f"[bold]Slots:[/] {slot_spacing}mm spacing\n")
    
    # Configure MVP3
    mvp3_config = MVP3Config(
        layer_count=layers,
        cell_size_mm=cell_size,
        slot_spacing_mm=slot_spacing,
    )
    
    # Create runner
    runner = MVP3Runner(
        pcb_path=input_pcb,
        config_path=config,
        output_path=output,
        mvp3_config=mvp3_config,
    )
    
    # Execute pipeline
    console.print("[bold cyan]Running deterministic pipeline...[/]")
    result = runner.run()
    
    if result.success:
        console.print("\n[bold green]✓ Pipeline completed successfully![/]")
        console.print(f"  Components placed: {result.components_placed}/{result.total_components}")
        console.print(f"  Nets routed: {result.nets_routed}/{result.total_nets}")
        
        if result.total_nets > 0:
            completion = 100 * result.nets_routed / result.total_nets
            console.print(f"  Routing completion: {completion:.1f}%")
        
        console.print(f"\n[bold]Output:[/] {output}")
    else:
        console.print(f"\n[bold red]✗ Pipeline failed:[/] {result.error}")
        raise click.Abort()
