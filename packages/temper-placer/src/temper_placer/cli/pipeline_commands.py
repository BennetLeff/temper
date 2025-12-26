import json
from pathlib import Path

import click

from temper_placer.pipeline.orchestrator import PipelineOrchestrator
from temper_placer.pipeline.state import PipelineConfig, PipelinePhase
from temper_placer.pipeline.visualization import RichDashboard, TerminalProgress


@click.command()
@click.argument("input_pcb", type=click.Path(exists=True))
@click.option("--loops", "-l", type=click.Path(), help="Loop definitions YAML")
@click.option("--constraints", "-c", type=click.Path(), help="PCL constraints YAML")
@click.option("--fab", type=str, default="jlcpcb_standard", help="Fab preset")
@click.option("--output", "-o", type=click.Path(), help="Output PCB file")
@click.option("--report", type=click.Path(), help="HTML report output")
@click.option("--trace", type=click.Path(), help="Decision trace JSON")
@click.option("--max-iterations", type=int, default=5, help="Max placement-routing iterations")
@click.option("--epochs", type=int, default=8000, help="Optimization epochs per iteration")
@click.option("--seed", type=int, default=42, help="Random seed")
@click.option("--dry-run", is_flag=True, help="Check feasibility only")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option("--visualize", is_flag=True, help="Show real-time dashboard")
def pipeline(
    input_pcb: str,
    loops: str,
    constraints: str,
    fab: str,
    output: str,
    report: str,
    trace: str,
    max_iterations: int,
    epochs: int,
    seed: int,
    dry_run: bool,
    verbose: bool,
    visualize: bool
):
    """Run the full placement pipeline."""

    config = PipelineConfig(
        input_pcb=Path(input_pcb),
        loops_yaml=Path(loops) if loops else None,
        constraints_yaml=Path(constraints) if constraints else None,
        output_pcb=Path(output) if output else None,
        output_report=Path(report) if report else None,
        output_trace=Path(trace) if trace else None,
        max_iterations=max_iterations,
        epochs=epochs,
        seed=seed,
        fab_preset=fab,
        dry_run=dry_run,
    )

    orchestrator = PipelineOrchestrator(config)

    if visualize:
        from rich.live import Live
        dashboard = RichDashboard()
        orchestrator.on_phase_start = dashboard.on_phase_start
        orchestrator.on_iteration = dashboard.on_iteration
        orchestrator.on_epoch = dashboard.on_epoch

        with Live(dashboard.create_layout(), refresh_per_second=4) as live:
            # Wrap on_epoch to also refresh the live display
            orig_on_epoch = orchestrator.on_epoch
            def on_epoch_wrapper(metrics):
                orig_on_epoch(metrics)
                dashboard.update()
            orchestrator.on_epoch = on_epoch_wrapper

            result = orchestrator.run()
    else:
        if verbose:
            progress = TerminalProgress(total_phases=8)
            orchestrator.on_phase_start = progress.on_phase_start
            orchestrator.on_phase_complete = progress.on_phase_complete
            orchestrator.on_iteration = progress.on_iteration
            orchestrator.on_epoch = progress.on_epoch

        result = orchestrator.run()

    if result.success:
        click.echo(click.style("SUCCESS", fg="green"))
        if output:
            click.echo(f"Output: {output}")
    else:
        click.echo(click.style(f"FAILED: {result.failure_reason}", fg="red"))
        raise SystemExit(1)

@click.group()
def phase():
    """Run individual pipeline phases."""
    pass

@phase.command()
@click.argument("input_pcb", type=click.Path(exists=True))
@click.option("--loops", "-l", type=click.Path(), help="Loop definitions")
@click.option("--output", "-o", type=click.Path(), help="Output JSON")
def semantic(input_pcb: str, loops: str, output: str):
    """Run semantic extraction phase."""
    config = PipelineConfig(
        input_pcb=Path(input_pcb),
        loops_yaml=Path(loops) if loops else None
    )
    orchestrator = PipelineOrchestrator(config)

    # Run input phase first
    state = orchestrator.phases[PipelinePhase.INPUT](orchestrator.state)
    # Run semantic phase
    state = orchestrator.phases[PipelinePhase.SEMANTIC](state)

    # Output result (loops)
    result = {
        "loops": state.loops, # Assuming loop extraction populates this
        "success": state.success
    }

    if output:
        with open(output, 'w') as f:
            json.dump(result, f, indent=2, default=str)
    else:
        click.echo(json.dumps(result, indent=2, default=str))

@phase.command()
@click.argument("input_pcb", type=click.Path(exists=True))
@click.option("--constraints", "-c", type=click.Path(), help="PCL constraints")
@click.option("--output", "-o", type=click.Path(), help="Output JSON")
def topological(input_pcb: str, constraints: str, output: str):
    """Run topological placement phase."""
    config = PipelineConfig(
        input_pcb=Path(input_pcb),
        constraints_yaml=Path(constraints) if constraints else None
    )
    orchestrator = PipelineOrchestrator(config)

    state = orchestrator.phases[PipelinePhase.INPUT](orchestrator.state)
    state = orchestrator.phases[PipelinePhase.TOPOLOGICAL](state)

    # TODO: Serialize topological result
    result = {"status": "topological phase completed (placeholder)"}

    if output:
        with open(output, 'w') as f:
            json.dump(result, f, indent=2)
    else:
        click.echo(json.dumps(result, indent=2))

@phase.command()
@click.argument("input_pcb", type=click.Path(exists=True))
@click.option("--epochs", type=int, default=8000, help="Optimization epochs")
@click.option("--seed", type=int, default=42, help="Random seed")
@click.option("--visualize", is_flag=True, help="Enable visualization")
@click.option("--output", "-o", type=click.Path(), help="Output PCB")
def geometric(input_pcb: str, epochs: int, seed: int, visualize: bool, output: str):
    """Run geometric optimization phase."""
    config = PipelineConfig(
        input_pcb=Path(input_pcb),
        output_pcb=Path(output) if output else None,
        epochs=epochs,
        seed=seed
    )
    orchestrator = PipelineOrchestrator(config)

    state = orchestrator.phases[PipelinePhase.INPUT](orchestrator.state)

    if visualize:
        click.echo("Visualization not yet integrated in pipeline phase command.")

    state = orchestrator.phases[PipelinePhase.GEOMETRIC](state)

    # To save output, we need to run OUTPUT phase or call export manually
    if output and state.placement_state:
        from temper_placer.io.kicad_writer import export_placements
        export_placements(
            template_pcb=config.input_pcb,
            output_pcb=Path(output),
            state=state.placement_state,
            component_refs=[c.ref for c in state.netlist.components],
            origin=state.board.origin
        )
        click.echo(f"Output saved to {output}")

@phase.command()
@click.argument("input_pcb", type=click.Path(exists=True))
@click.option("--level", type=int, default=2, help="Verification level (1-3)")
@click.option("--output", "-o", type=click.Path(), help="Output report")
def routing(input_pcb: str, level: int, output: str):
    """Run routing verification phase."""
    # Note: 'level' is not yet used by the orchestrator
    config = PipelineConfig(
        input_pcb=Path(input_pcb)
    )
    orchestrator = PipelineOrchestrator(config)

    state = orchestrator.phases[PipelinePhase.INPUT](orchestrator.state)
    # We need placement state for routing check.
    # But routing phase usually runs AFTER geometric.
    # If we run it on input_pcb, we assume input_pcb is already placed?
    # The current pipeline assumes placement is generated in GEOMETRIC phase.

    # If the user wants to check an existing PCB, we need to load placements from it.
    # parse_kicad_pcb loads positions into netlist/board.
    # We need to construct PlacementState from that.

    # For now, we'll try to run routing phase.
    # _run_routing needs state.placement_state.

    # Create pseudo placement state from input
    import jax.numpy as jnp

    from temper_placer.core.state import PlacementState

    # Extract positions from loaded components
    positions = []
    # We need to sort by component index to match netlist order
    # netlist.components is ordered.
    for comp in state.netlist.components:
        pos = comp.initial_position or (0.0, 0.0)
        positions.append(pos)

    state.placement_state = PlacementState(
        positions=jnp.array(positions),
        rotation_logits=jnp.zeros((len(positions), 4), dtype=jnp.float32)
    )

    state = orchestrator.phases[PipelinePhase.ROUTING](state)

    if output:
        # TODO: Save routing report
        with open(output, 'w') as f:
            f.write(str(state.routing_report))
    else:
        click.echo(state.routing_report)
