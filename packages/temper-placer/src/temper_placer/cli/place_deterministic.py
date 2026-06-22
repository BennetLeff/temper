"""place-deterministic command for temper-placer CLI."""

from __future__ import annotations

import click
from pathlib import Path
from ._io import console
from ._io import Panel

@click.command("place-deterministic")
@click.argument("input_pcb", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-c",
    "--config",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Constraint configuration YAML file.",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    required=True,
    help="Output .kicad_pcb file path.",
)
@click.option(
    "--drc-aware/--no-drc-aware",
    default=True,
    help="Enable DRC-aware routing using DRCOracle integration.",
)
@click.option(
    "--seed",
    type=int,
    default=42,
    help="Random seed for reproducibility (default: 42).",
)
def place_deterministic(
    input_pcb: Path,
    config: Path,
    output: Path,
    drc_aware: bool,
    seed: int,
) -> None:
    """
    Place components using hierarchical deterministic pipeline.

    This command runs:
    Zone-based Placement -> DRC-aware Sequential Routing -> Validation
    """
    from temper_placer.deterministic import (
        create_drc_aware_pipeline, 
        create_legacy_pipeline,
        BoardState
    )
    from temper_placer.io.config_loader import load_constraints, constraints_to_design_rules
    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.io.kicad_writer import (
        write_placements_to_pcb, 
        write_routes_to_pcb, 
        strip_routing, 
        PlacementUpdate,
        add_bounding_boxes_to_pcb,
        add_silkscreen_labels
    )
    
    console.print(
        Panel.fit(
            f"[bold cyan]Deterministic Placement Pipeline ({'DRC-aware' if drc_aware else 'Legacy'})[/]",
            subtitle=f"v{__version__}"
        )
    )

    try:
        # 1. Load constraints and design rules
        console.print(f"  [dim]Loading constraints from {config}...[/]")
        constraints = load_constraints(config)
        design_rules = constraints_to_design_rules(constraints)

        # 2. Extract KiCad metadata for DRC oracle
        from temper_placer.io.kicad_metadata import extract_kicad_metadata
        console.print(f"  [dim]Extracting KiCad metadata...[/]")
        metadata = extract_kicad_metadata(input_pcb)

        # 3. Create pipeline
        if drc_aware:
            pipeline = create_drc_aware_pipeline(
                design_rules=design_rules,
                config=constraints,
                metadata=metadata,
                zone_aware=True,
            )
        else:
            pipeline = create_legacy_pipeline()

        # 4. Parse PCB
        console.print(f"  [dim]Parsing PCB {input_pcb}...[/]")
        parse_result = parse_kicad_pcb(input_pcb)
        initial_state = BoardState(board=parse_result.board, netlist=parse_result.netlist)
        
        # 4. Run pipeline
        console.print("[bold cyan]Running pipeline stages...[/]")
        final_state = pipeline.run(initial_state)
        
        # 5. Export results
        console.print("[bold cyan]Exporting results...[/]")
        
        # Strip existing routing first to ensure clean output
        strip_routing(input_pcb, output, keep_zones=True)
        
        # Export placements
        placements_dict = {
            ref: PlacementUpdate(ref=ref, x=pos[0], y=pos[1], rotation=0.0) 
            for ref, pos in (final_state.placements or [])
        }
        write_placements_to_pcb(output, output, placements_dict)
        
        # Export routes
        if final_state.routes:
            write_routes_to_pcb(output, output, final_state.routes, final_state.vias)
            
        # Add visual enhancements
        add_bounding_boxes_to_pcb(output)
        add_silkscreen_labels(output)
            
        console.print(f"\n[bold green]✓ Pipeline completed![/] Output: {output}")

    except Exception as e:
        console.print(f"\n[bold red]Error:[/] {e}")
        import traceback
        console.print(traceback.format_exc())
        raise click.Abort() from e


# =============================================================================
# Version Command
# =============================================================================
