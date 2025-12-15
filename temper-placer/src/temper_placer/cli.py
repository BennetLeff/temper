"""
Command-line interface for temper-placer.

Usage:
    temper-placer optimize INPUT -c CONFIG -o OUTPUT [--visualize]
    temper-placer validate INPUT [--drc] [--ngspice]
    temper-placer export --placements PLACEMENTS --pcb TEMPLATE -o OUTPUT
    temper-placer info INPUT
"""

from __future__ import annotations

import json
import signal
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.panel import Panel

from temper_placer import __version__

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="temper-placer")
def main() -> None:
    """temper-placer: JAX-based PCB placement optimizer."""
    pass


@main.command()
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
    "--epochs",
    "-n",
    type=int,
    default=8000,
    help="Number of optimization epochs (default: 8000).",
)
@click.option(
    "--visualize",
    "-v",
    is_flag=True,
    default=False,
    help="Enable live browser visualization (not yet implemented).",
)
@click.option(
    "--port",
    type=int,
    default=8080,
    help="Port for visualization server.",
)
@click.option(
    "--seed",
    type=int,
    default=42,
    help="Random seed for reproducibility.",
)
@click.option(
    "--checkpoint",
    type=click.Path(path_type=Path),
    help="Save checkpoint file (JSON format).",
)
@click.option(
    "--curriculum/--no-curriculum",
    default=True,
    help="Use curriculum learning (default: enabled).",
)
@click.option(
    "--placements-json",
    type=click.Path(path_type=Path),
    help="Also save placements as JSON file.",
)
def optimize(
    input_pcb: Path,
    config: Path,
    output: Path,
    epochs: int,
    visualize: bool,
    port: int,
    seed: int,
    checkpoint: Optional[Path],
    curriculum: bool,
    placements_json: Optional[Path],
) -> None:
    """
    Optimize component placement for a KiCad PCB.

    Reads INPUT_PCB and constraint CONFIG, runs gradient-based optimization,
    and writes the result to OUTPUT.

    Example:
        temper-placer optimize temper.kicad_pcb -c constraints.yaml -o optimized.kicad_pcb
    """
    console.print(
        Panel.fit(
            f"[bold blue]temper-placer[/] v{__version__}\nJAX-based PCB placement optimizer",
            border_style="blue",
        )
    )

    console.print(f"\n[bold]Input:[/] {input_pcb}")
    console.print(f"[bold]Config:[/] {config}")
    console.print(f"[bold]Output:[/] {output}")
    console.print(f"[bold]Epochs:[/] {epochs}")
    console.print(f"[bold]Seed:[/] {seed}")
    console.print(f"[bold]Curriculum:[/] {'enabled' if curriculum else 'disabled'}")

    # Import heavy dependencies only when needed
    console.print("\n[dim]Loading JAX and optimizer modules...[/]")

    try:
        import jax
        import jax.numpy as jnp
        from temper_placer.io.kicad_parser import parse_kicad_pcb
        from temper_placer.io.config_loader import load_constraints, create_board_from_constraints
        from temper_placer.io.kicad_writer import (
            export_placements,
            placements_to_json,
            state_to_placements,
        )
        from temper_placer.optimizer import train, train_multiphase, OptimizerConfig
        from temper_placer.optimizer.curriculum import create_default_phases, create_fast_phases
        from temper_placer.losses import (
            CompositeLoss,
            WeightedLoss,
            OverlapLoss,
            BoundaryLoss,
            WirelengthLoss,
            SpreadLoss,
        )
        from temper_placer.losses.base import LossContext
    except ImportError as e:
        console.print(f"[red]Failed to import required modules: {e}[/]")
        console.print("Please ensure JAX and all dependencies are installed:")
        console.print("  pip install temper-placer")
        sys.exit(1)

    # Step 1: Parse KiCad PCB
    console.print("\n[bold cyan]Step 1/5:[/] Parsing KiCad PCB...")
    try:
        parse_result = parse_kicad_pcb(input_pcb)
        netlist = parse_result.netlist
        board_from_pcb = parse_result.board

        if parse_result.has_warnings:
            for w in parse_result.warnings:
                console.print(f"  [yellow]Warning:[/] {w}")

        console.print(
            f"  [green]✓[/] Loaded {netlist.n_components} components, {netlist.n_nets} nets"
        )
    except Exception as e:
        console.print(f"[red]Failed to parse PCB: {e}[/]")
        sys.exit(1)

    # Step 2: Load constraints
    console.print("\n[bold cyan]Step 2/5:[/] Loading constraints...")
    try:
        constraints = load_constraints(config)
        board = create_board_from_constraints(constraints)

        console.print(f"  [green]✓[/] Board: {board.width:.1f}mm x {board.height:.1f}mm")
        console.print(f"  [green]✓[/] Zones: {len(board.zones)}")
        console.print(f"  [green]✓[/] HV clearance: {constraints.hv_clearance_mm}mm")
    except Exception as e:
        console.print(f"[red]Failed to load constraints: {e}[/]")
        sys.exit(1)

    # Step 3: Create loss functions
    console.print("\n[bold cyan]Step 3/5:[/] Creating loss functions...")

    # Build composite loss with curriculum-aware weights
    def make_loss(weights: dict) -> CompositeLoss:
        """Factory function for curriculum learning."""
        losses = []

        # Core feasibility losses
        if "overlap" in weights:
            losses.append(WeightedLoss(OverlapLoss(), weight=weights["overlap"]))
        if "boundary" in weights:
            losses.append(WeightedLoss(BoundaryLoss(), weight=weights["boundary"]))

        # Performance losses
        if "wirelength" in weights:
            losses.append(WeightedLoss(WirelengthLoss(), weight=weights["wirelength"]))
        if "spread" in weights:
            losses.append(WeightedLoss(SpreadLoss(), weight=weights["spread"]))

        # Add more losses based on constraints
        # (clearance, thermal, zone, loop_area, etc. can be added here)

        return CompositeLoss(losses)

    # Default weights for non-curriculum mode
    default_weights = {
        "overlap": 100.0,
        "boundary": 50.0,
        "wirelength": 10.0,
        "spread": 5.0,
    }

    composite_loss = make_loss(default_weights)
    console.print(f"  [green]✓[/] Created {len(composite_loss.losses)} loss functions")

    # Step 4: Create optimizer config and context
    console.print("\n[bold cyan]Step 4/5:[/] Initializing optimizer...")

    context = LossContext.from_netlist_and_board(netlist, board)

    # Configure optimizer
    if curriculum:
        phases = create_default_phases(epochs)
        cfg = OptimizerConfig(
            epochs=epochs,
            seed=seed,
            log_interval=max(1, epochs // 100),  # Log ~100 times
            curriculum_phases=phases,
        )
        console.print(f"  [green]✓[/] Curriculum: {len(phases)} phases")
    else:
        cfg = OptimizerConfig(
            epochs=epochs,
            seed=seed,
            log_interval=max(1, epochs // 100),
        )

    console.print(
        f"  [green]✓[/] Temperature: {cfg.temperature.initial:.1f} → {cfg.temperature.final:.2f}"
    )
    console.print(f"  [green]✓[/] Learning rate: {cfg.learning_rate.initial:.4f}")

    # Step 5: Run optimization
    console.print("\n[bold cyan]Step 5/5:[/] Running optimization...")

    # Setup Ctrl+C handler for graceful interruption
    interrupted = False

    def signal_handler(sig, frame):
        nonlocal interrupted
        interrupted = True
        console.print("\n[yellow]Interrupted! Saving current best state...[/]")

    original_handler = signal.signal(signal.SIGINT, signal_handler)

    # Progress callback
    last_printed_epoch = -1

    def progress_callback(metrics):
        nonlocal last_printed_epoch
        if interrupted:
            raise KeyboardInterrupt()

        # Print every 10% of epochs
        print_interval = max(1, epochs // 10)
        if metrics.epoch % print_interval == 0 or metrics.epoch == epochs - 1:
            phase_name = ""
            if curriculum and cfg.curriculum_phases:
                for p in cfg.curriculum_phases:
                    if p.start_epoch <= metrics.epoch < p.end_epoch:
                        phase_name = f" [{p.name}]"
                        break

            console.print(
                f"  Epoch {metrics.epoch:5d}/{epochs}: "
                f"loss={metrics.loss:8.2f}, "
                f"T={metrics.temperature:.3f}, "
                f"lr={metrics.learning_rate:.5f}"
                f"{phase_name}"
            )

    try:
        if curriculum and cfg.curriculum_phases:
            result = train_multiphase(
                netlist,
                board,
                make_loss,
                context,
                cfg,
                callback=progress_callback,
            )
        else:
            result = train(
                netlist,
                board,
                composite_loss,
                context,
                cfg,
                callback=progress_callback,
            )

        # Restore signal handler
        signal.signal(signal.SIGINT, original_handler)

        console.print(f"\n  [green]✓[/] Optimization complete!")
        console.print(f"    Final loss: {result.final_loss:.4f}")
        console.print(f"    Best loss: {result.best_loss:.4f}")
        console.print(f"    Epochs: {result.total_epochs}")
        console.print(f"    Converged: {'yes' if result.converged else 'no'}")
        console.print(f"    Time: {result.elapsed_seconds:.1f}s")

    except KeyboardInterrupt:
        signal.signal(signal.SIGINT, original_handler)
        console.print("[yellow]Optimization interrupted.[/]")
        # Use best state found so far
        if "result" not in locals():
            console.print("[red]No results available yet.[/]")
            sys.exit(1)
    except Exception as e:
        signal.signal(signal.SIGINT, original_handler)
        console.print(f"[red]Optimization failed: {e}[/]")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    # Export results
    console.print("\n[bold cyan]Exporting results...[/]")

    # Get component refs in order
    component_refs = [c.ref for c in netlist.components]

    # Get board origin
    origin = board_from_pcb.origin if board_from_pcb else (0.0, 0.0)

    try:
        # Export to KiCad PCB
        write_result = export_placements(
            template_pcb=input_pcb,
            output_pcb=output,
            state=result.best_state,
            component_refs=component_refs,
            origin=origin,
        )

        console.print(f"  [green]✓[/] Wrote {output}")
        console.print(f"    Updated: {write_result.components_updated} components")
        console.print(f"    Skipped: {write_result.components_skipped} components")

        if write_result.has_warnings:
            for w in write_result.warnings:
                console.print(f"    [yellow]Warning:[/] {w}")

        # Also save JSON if requested
        if placements_json:
            placements = state_to_placements(result.best_state, component_refs, origin)
            placements_dict = placements_to_json(placements)

            placements_json.parent.mkdir(parents=True, exist_ok=True)
            with open(placements_json, "w") as f:
                json.dump(placements_dict, f, indent=2)

            console.print(f"  [green]✓[/] Wrote {placements_json}")

        # Save checkpoint if requested
        if checkpoint:
            checkpoint_data = {
                "epochs": result.total_epochs,
                "final_loss": result.final_loss,
                "best_loss": result.best_loss,
                "converged": result.converged,
                "elapsed_seconds": result.elapsed_seconds,
                "config": {
                    "seed": seed,
                    "epochs": epochs,
                    "curriculum": curriculum,
                },
            }

            checkpoint.parent.mkdir(parents=True, exist_ok=True)
            with open(checkpoint, "w") as f:
                json.dump(checkpoint_data, f, indent=2)

            console.print(f"  [green]✓[/] Wrote {checkpoint}")

    except Exception as e:
        console.print(f"[red]Failed to export results: {e}[/]")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    console.print("\n[bold green]Done![/]")


@main.command()
@click.option(
    "--placements",
    "-p",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Placements JSON file (from optimize command).",
)
@click.option(
    "--pcb",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Template KiCad PCB file.",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    required=True,
    help="Output .kicad_pcb file path.",
)
def export(
    placements: Path,
    pcb: Path,
    output: Path,
) -> None:
    """
    Export placements JSON to a KiCad PCB file.

    This command applies a placements JSON file (generated by the optimize
    command) to a template PCB file.

    Example:
        temper-placer export -p placements.json --pcb template.kicad_pcb -o output.kicad_pcb
    """
    console.print(f"[bold blue]temper-placer export[/] v{__version__}")

    try:
        import json
        from temper_placer.io.kicad_writer import (
            placements_from_json,
            write_placements_to_pcb,
        )

        # Load placements
        with open(placements, "r") as f:
            placements_data = json.load(f)

        placements_dict = placements_from_json(placements_data)
        console.print(f"[green]✓[/] Loaded {len(placements_dict)} placements")

        # Write to PCB
        result = write_placements_to_pcb(pcb, output, placements_dict)

        console.print(f"[green]✓[/] Wrote {output}")
        console.print(f"  Updated: {result.components_updated}")
        console.print(f"  Skipped: {result.components_skipped}")

        if result.has_warnings:
            for w in result.warnings:
                console.print(f"  [yellow]Warning:[/] {w}")

    except Exception as e:
        console.print(f"[red]Failed: {e}[/]")
        sys.exit(1)


@main.command()
@click.argument("input_pcb", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--drc/--no-drc",
    default=True,
    help="Run KiCad DRC validation.",
)
@click.option(
    "--ngspice/--no-ngspice",
    default=False,
    help="Run ngspice electrical validation.",
)
def validate(
    input_pcb: Path,
    drc: bool,
    ngspice: bool,
) -> None:
    """
    Validate a placed PCB file.

    Runs KiCad DRC and optionally ngspice simulation to check placement.

    Example:
        temper-placer validate optimized.kicad_pcb --drc --ngspice
    """
    console.print(f"[bold blue]Validating:[/] {input_pcb}")

    if drc:
        console.print("\n[bold]KiCad DRC:[/]")
        # TODO: Run kicad-cli pcb drc
        console.print("[yellow]DRC validation not yet implemented.[/]")
        console.print("To run manually: kicad-cli pcb drc input.kicad_pcb -o drc_report.txt")

    if ngspice:
        console.print("\n[bold]ngspice Validation:[/]")
        # TODO: Run ngspice simulations
        console.print("[yellow]ngspice validation not yet implemented.[/]")


@main.command()
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


@main.command()
def version() -> None:
    """Show version information."""
    console.print(f"temper-placer v{__version__}")

    try:
        import jax

        console.print(f"JAX v{jax.__version__}")
        console.print(f"  Backend: {jax.default_backend()}")
        console.print(f"  Devices: {jax.device_count()}")
    except ImportError:
        console.print("JAX: [red]not installed[/]")

    try:
        import optax

        console.print(f"optax v{optax.__version__}")
    except ImportError:
        console.print("optax: [red]not installed[/]")


if __name__ == "__main__":
    main()
