"""pipeline command for temper-placer CLI."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

import click

from ._io import console

if TYPE_CHECKING:
    from temper_placer.pipeline.orchestrator import (
        PipelineConfig,
        PipelineOrchestrator,
        PipelinePhase,
        PipelineState,
    )
    from temper_placer.pipeline.visualization import RichDashboard

@click.command()
@click.argument("input_pcb", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-l",
    "--loops",
    type=click.Path(exists=True, path_type=Path),
    help="Loop definitions YAML file.",
)
@click.option(
    "-c",
    "--constraints",
    type=click.Path(exists=True, path_type=Path),
    help="PCL constraints YAML file.",
)
@click.option(
    "--fab",
    type=str,
    default="jlcpcb_standard",
    help="Manufacturing fab preset (default: jlcpcb_standard).",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="Output .kicad_pcb file path.",
)
@click.option(
    "--report",
    type=click.Path(path_type=Path),
    help="HTML report output path.",
)
@click.option(
    "--trace",
    type=click.Path(path_type=Path),
    help="Decision trace JSON output path.",
)
@click.option(
    "--max-iterations",
    type=int,
    default=5,
    help="Maximum placement-routing iterations (default: 5).",
)
@click.option(
    "--epochs",
    "-n",
    type=int,
    default=8000,
    help="Optimization epochs per iteration (default: 8000).",
)
@click.option(
    "--seed",
    type=int,
    default=42,
    help="Random seed for reproducibility (default: 42).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Check feasibility only (preflight check, no optimization).",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    default=False,
    help="Show detailed progress output.",
)
def pipeline(
    input_pcb: Path,
    loops: Path | None,
    constraints: Path | None,
    fab: str,
    output: Path | None,
    report: Path | None,
    trace: Path | None,
    max_iterations: int,
    epochs: int,
    seed: int,
    dry_run: bool,
    verbose: bool,
) -> None:
    """Run the full placement pipeline.

    This command runs the complete placement pipeline:
    Input -> Semantic -> Topological -> Preflight -> Geometric -> Routing -> Output

    Use --dry-run to check feasibility without full optimization.
    """
    # Create pipeline configuration
    config = PipelineConfig(
        input_pcb=input_pcb,
        loops_yaml=loops,
        constraints_yaml=constraints,
        output_pcb=output,
        output_report=report,
        output_trace=trace,
        max_iterations=max_iterations,
        epochs=epochs,
        seed=seed,
        fab_preset=fab,
        dry_run=dry_run,
    )

    # Create orchestrator
    orchestrator = PipelineOrchestrator(config)

    # Set up verbose callbacks using visualization classes
    if verbose:
        # Use RichDashboard for rich terminal output
        dashboard = RichDashboard()

        def on_phase_start(phase: PipelinePhase, state: PipelineState) -> None:
            dashboard.on_phase_start(phase.value, state)

        def on_phase_complete(phase: PipelinePhase, state: PipelineState) -> None:
            elapsed = state.phase_timings.get(phase, 0)
            dashboard.on_phase_complete(phase.value, state)
            console.print(f"    ({elapsed:.2f}s)")

        def on_iteration(iteration: int, state: PipelineState) -> None:
            dashboard.on_iteration(iteration, state)

        def on_epoch(epoch: int, loss: float) -> None:
            dashboard.on_epoch(epoch, loss)
            # Print every 500 epochs for verbose output
            if epoch % 500 == 0:
                console.print(f"      Epoch {epoch}: loss={loss:.4f}")

        orchestrator.on_phase_start = on_phase_start
        orchestrator.on_phase_complete = on_phase_complete
        orchestrator.on_iteration = on_iteration
        # Note: on_epoch is set if orchestrator supports it

    # Run the pipeline
    try:
        result = orchestrator.run()

        if result.success:
            console.print(Panel("[green bold]SUCCESS[/]", title="Pipeline Result"))
            if output:
                console.print(f"  Output: {output}")
            if dry_run:
                console.print("  Feasibility: [green]FEASIBLE[/]")
        else:
            console.print(
                Panel(f"[red bold]FAILED[/]\n{result.failure_reason}", title="Pipeline Result")
            )
            if result.failed_phase:
                console.print(f"  Failed phase: {result.failed_phase.value}")
            sys.exit(1)

    except Exception as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)
