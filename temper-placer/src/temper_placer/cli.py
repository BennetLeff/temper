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
@click.option(
    "--heuristics/--no-heuristics",
    default=True,
    help="Use smart heuristic initialization (default: enabled).",
)
@click.option(
    "--auto-group/--no-auto-group",
    default=True,
    help="Automatically detect and cluster functional blocks (default: enabled).",
)
@click.option(
    "--centrality/--no-centrality",
    default=False,
    help="Use graph centrality to prioritize hub components (default: disabled).",
)
@click.option(
    "--profile-dir",
    type=click.Path(path_type=Path),
    help="Save JAX profiler trace to this directory.",
)
@click.option(
    "--grad-norm/--no-grad-norm",
    default=False,
    help="Use GradNorm adaptive loss weighting (default: disabled).",
)
@click.option(
    "--grad-norm-alpha",
    type=float,
    default=1.5,
    help="GradNorm asymmetry parameter (default: 1.5).",
)
@click.option(
    "--grad-norm-lr",
    type=float,
    default=0.025,
    help="GradNorm weight update learning rate (default: 0.025).",
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
    heuristics: bool,
    auto_group: bool,
    centrality: bool,
    profile_dir: Optional[Path],
    grad_norm: bool,
    grad_norm_alpha: float,
    grad_norm_lr: float,
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
    console.print(f"[bold]Heuristics:[/] {'enabled' if heuristics else 'disabled'}")
    console.print(f"[bold]Centrality:[/] {'enabled' if centrality else 'disabled'}")

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
            GroupClusterLoss,
            GroupConfig,
        )
        from temper_placer.losses.base import LossContext
        from temper_placer.heuristics import create_default_pipeline, PlacementContext
        from temper_placer.core.state import PlacementState
        from temper_placer.core.community import detect_communities
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

    # Step 2b: Run heuristic initialization (if enabled)
    initial_state: Optional[PlacementState] = None
    if heuristics:
        console.print("\n[bold cyan]Step 2b/5:[/] Running smart initialization heuristics...")
        try:
            pipeline = create_default_pipeline()
            heuristic_key = jax.random.PRNGKey(seed)

            pipeline_result = pipeline.run(
                board=board,
                netlist=netlist,
                constraints=constraints,
                key=heuristic_key,
            )
            initial_state = pipeline_result.state

            # Report heuristic results
            total_placed = sum(
                stats.get("placed", 0) for stats in pipeline_result.heuristic_stats.values()
            )
            console.print(f"  [green]✓[/] Placed {total_placed}/{netlist.n_components} components")

            # Show per-heuristic stats
            for name, stats in pipeline_result.heuristic_stats.items():
                if stats.get("placed", 0) > 0:
                    console.print(f"    - {name}: {stats['placed']} placed")

            if pipeline_result.unplaced:
                console.print(
                    f"  [yellow]Warning:[/] {len(pipeline_result.unplaced)} components unplaced"
                )

            if pipeline_result.conflicts:
                console.print(f"  [dim]Resolved {len(pipeline_result.conflicts)} conflicts[/]")

        except Exception as e:
            console.print(f"[yellow]Warning:[/] Heuristics failed, using random init: {e}")
            initial_state = None

    # Step 3: Create loss functions
    console.print("\n[bold cyan]Step 3/5:[/] Creating loss functions...")

    # Run auto-grouping if requested
    detected_communities = []
    if auto_group:
        console.print("  [dim]Detecting functional communities (Louvain)...[/]")
        detected_communities = detect_communities(netlist)
        if detected_communities:
            console.print(f"  [green]✓[/] Detected {len(detected_communities)} functional blocks")
            for comm in detected_communities:
                console.print(f"    - {comm.name}: {len(comm.component_refs)} components")

    # Build composite loss with curriculum-aware weights
    def make_loss(weights: dict) -> CompositeLoss:
        """Factory function for curriculum learning."""
        losses = []

        # Core feasibility losses
        if "overlap" in weights:
            # Use margin=1.0mm for DRC safety (KiCad default clearance is 0.2mm)
            # The 1.0mm margin provides headroom for:
            # - 0.2mm KiCad clearance
            # - Pad extensions beyond bounding box (~0.3-0.5mm)
            # - Solder mask aperture bridges
            # rotation_invariant=True ensures overlap is detected regardless of rotation
            losses.append(
                WeightedLoss(
                    OverlapLoss(margin=1.0, rotation_invariant=True), weight=weights["overlap"]
                )
            )
        if "boundary" in weights:
            losses.append(WeightedLoss(BoundaryLoss(), weight=weights["boundary"]))

        # Performance losses
        if "wirelength" in weights:
            losses.append(WeightedLoss(WirelengthLoss(), weight=weights["wirelength"]))
        if "spread" in weights:
            losses.append(WeightedLoss(SpreadLoss(), weight=weights["spread"]))

        # Auto-grouping clusters
        if auto_group and detected_communities:
            group_configs = []
            for comm in detected_communities:
                # Resolve refs to indices
                indices = [netlist.get_component_index(ref) for ref in comm.component_refs]
                group_configs.append(
                    GroupConfig(
                        name=comm.name,
                        component_indices=jnp.array(indices, dtype=jnp.int32),
                        max_diameter_mm=30.0,  # Default 30mm cluster size
                        weight=1.0,
                    )
                )
            losses.append(WeightedLoss(GroupClusterLoss(group_configs), weight=10.0))

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

    context = LossContext.from_netlist_and_board(
        netlist, board, use_centrality_weighting=centrality
    )

    # Configure optimizer
    from temper_placer.optimizer.config import GradNormConfig
    
    gn_cfg = GradNormConfig(alpha=grad_norm_alpha, learning_rate=grad_norm_lr)

    if curriculum:
        phases = create_default_phases(epochs)
        cfg = OptimizerConfig(
            epochs=epochs,
            seed=seed,
            log_interval=max(1, epochs // 100),  # Log ~100 times
            curriculum_phases=phases,
            use_centrality_weighting=centrality,
            use_grad_norm=grad_norm,
            grad_norm=gn_cfg,
        )
        console.print(f"  [green]✓[/] Curriculum: {len(phases)} phases")
    else:
        cfg = OptimizerConfig(
            epochs=epochs,
            seed=seed,
            log_interval=max(1, epochs // 100),
            use_centrality_weighting=centrality,
            use_grad_norm=grad_norm,
            grad_norm=gn_cfg,
        )

    console.print(
        f"  [green]✓[/] Temperature: {cfg.temperature.start:.1f} → {cfg.temperature.end:.2f}"
    )
    console.print(f"  [green]✓[/] Learning rate: {cfg.learning_rate.initial:.4f}")

    # Step 5: Run optimization
    console.print("\n[bold cyan]Step 5/5:[/] Running optimization...")
    if profile_dir:
        console.print(f"  [dim]JAX profiler enabled, saving to: {profile_dir}[/]")

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
        profile_dir_str = str(profile_dir) if profile_dir else None
        if curriculum and cfg.curriculum_phases:
            result = train_multiphase(
                netlist,
                board,
                make_loss,
                context,
                cfg,
                initial_state=initial_state,
                callback=progress_callback,
                profile_dir=profile_dir_str,
            )
        else:
            result = train(
                netlist,
                board,
                composite_loss,
                context,
                cfg,
                initial_state=initial_state,
                callback=progress_callback,
                profile_dir=profile_dir_str,
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
    "-c",
    "--config",
    type=click.Path(exists=True, path_type=Path),
    help="Constraint configuration YAML file (for constraint validation).",
)
@click.option(
    "--tools/--no-tools",
    default=True,
    help="Check external tool availability (kicad-cli, ngspice).",
)
@click.option(
    "--zones/--no-zones",
    default=True,
    help="Check zone assignments and boundaries.",
)
@click.option(
    "--constraints/--no-constraints",
    default=True,
    help="Check for impossible constraints.",
)
@click.option(
    "--drc/--no-drc",
    default=False,
    help="Run KiCad DRC validation (requires kicad-cli).",
)
@click.option(
    "--strict",
    is_flag=True,
    default=False,
    help="Treat warnings as errors (exit 1 on any issue).",
)
@click.option(
    "--json-output",
    is_flag=True,
    default=False,
    help="Output results as JSON.",
)
def validate(
    input_pcb: Path,
    config: Optional[Path],
    tools: bool,
    zones: bool,
    constraints: bool,
    drc: bool,
    strict: bool,
    json_output: bool,
) -> None:
    """
    Validate PCB and constraints before optimization.

    Runs pre-flight checks to catch issues before starting optimization:
    - External tool availability (kicad-cli, ngspice)
    - Zone assignments and boundaries
    - Constraint feasibility

    Exit codes: 0 = all checks passed, 1 = errors found

    Examples:
        temper-placer validate temper.kicad_pcb -c constraints.yaml
        temper-placer validate temper.kicad_pcb --tools --no-zones
        temper-placer validate optimized.kicad_pcb --drc
    """
    from temper_placer.validation.preflight import (
        PreflightSeverity,
        PreflightResult,
        check_external_tools,
        check_zones_fit_on_board,
        check_components_have_zones,
        check_impossible_constraints,
    )

    if not json_output:
        console.print(f"[bold blue]Validating:[/] {input_pcb}")

    result = PreflightResult(passed=True, issues=[])
    netlist = None
    constraints_obj = None

    # Parse PCB if needed for zone/constraint checks
    if zones or constraints:
        try:
            from temper_placer.io.kicad_parser import parse_kicad_pcb

            parse_result = parse_kicad_pcb(input_pcb)
            netlist = parse_result.netlist
            if not json_output:
                console.print(f"  [green]✓[/] Loaded {netlist.n_components} components")
        except Exception as e:
            if not json_output:
                console.print(f"[red]Failed to parse PCB: {e}[/]")
            sys.exit(1)

    # Load constraints if provided
    if config and (zones or constraints):
        try:
            from temper_placer.io.config_loader import load_constraints

            constraints_obj = load_constraints(config)
            if not json_output:
                console.print(
                    f"  [green]✓[/] Loaded constraints: {len(constraints_obj.zones)} zones"
                )
        except Exception as e:
            if not json_output:
                console.print(f"[red]Failed to load constraints: {e}[/]")
            sys.exit(1)

    # Run checks
    if tools:
        if not json_output:
            console.print("\n[bold cyan]External Tools:[/]")
        tool_result = check_external_tools()
        result = result.merge(tool_result)
        if not json_output:
            for issue in tool_result.issues:
                _print_issue(issue)

    if zones and constraints_obj:
        if not json_output:
            console.print("\n[bold cyan]Zone Boundaries:[/]")
        zone_result = check_zones_fit_on_board(constraints_obj)
        result = result.merge(zone_result)
        if not json_output:
            for issue in zone_result.issues:
                _print_issue(issue)

        if netlist:
            if not json_output:
                console.print("\n[bold cyan]Zone Assignments:[/]")
            assign_result = check_components_have_zones(
                netlist, constraints_obj, require_all=strict
            )
            result = result.merge(assign_result)
            if not json_output:
                for issue in assign_result.issues:
                    _print_issue(issue)

    if constraints and netlist and constraints_obj:
        if not json_output:
            console.print("\n[bold cyan]Constraint Feasibility:[/]")
        constraint_result = check_impossible_constraints(netlist, constraints_obj)
        result = result.merge(constraint_result)
        if not json_output:
            for issue in constraint_result.issues:
                _print_issue(issue)

    # Run DRC if requested
    if drc:
        if not json_output:
            console.print("\n[bold cyan]KiCad DRC:[/]")
        from temper_placer.validation.drc import KiCadDRCValidator

        drc_validator = KiCadDRCValidator()
        if drc_validator.is_available():
            drc_result = drc_validator.run_drc(input_pcb)
            if not json_output:
                console.print(
                    f"  DRC completed: {drc_result.error_count} errors, {drc_result.warning_count} warnings"
                )
            if drc_result.has_errors:
                result = PreflightResult(passed=False, issues=result.issues)
        else:
            if not json_output:
                console.print("  [yellow]kicad-cli not available - skipping DRC[/]")

    # Output results
    if json_output:
        import json as json_module

        output = {
            "passed": result.passed,
            "error_count": result.error_count,
            "warning_count": result.warning_count,
            "info_count": result.info_count,
            "issues": [
                {
                    "severity": i.severity.name.lower(),
                    "code": i.code,
                    "message": i.message,
                    "suggestion": i.suggestion,
                    "components": i.components,
                }
                for i in result.issues
            ],
        }
        print(json_module.dumps(output, indent=2))
    else:
        # Summary
        console.print("\n" + "─" * 50)
        if result.passed and (not strict or result.warning_count == 0):
            console.print("[bold green]✓ All checks passed[/]")
        else:
            console.print(f"[bold red]✗ Validation failed[/]")
        console.print(
            f"  {result.error_count} errors, {result.warning_count} warnings, {result.info_count} info"
        )

    # Exit code
    if strict:
        sys.exit(0 if result.passed and result.warning_count == 0 else 1)
    else:
        sys.exit(0 if result.passed else 1)


def _print_issue(issue) -> None:
    """Print a preflight issue with appropriate formatting."""
    from temper_placer.validation.preflight import PreflightSeverity

    if issue.severity == PreflightSeverity.INFO:
        console.print(f"  [dim]ℹ {issue.message}[/]")
    elif issue.severity == PreflightSeverity.WARNING:
        console.print(f"  [yellow]⚠ {issue.message}[/]")
        if issue.suggestion:
            console.print(f"    [dim]{issue.suggestion}[/]")
    elif issue.severity == PreflightSeverity.ERROR:
        console.print(f"  [red]✗ {issue.message}[/]")
        if issue.suggestion:
            console.print(f"    [dim]{issue.suggestion}[/]")


@main.command()
@click.option(
    "--pcbs",
    type=str,
    default="all",
    help="Comma-separated list of PCBs to benchmark (default: all).",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output report file (default: stdout).",
)
@click.option(
    "--format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Report format (default: text).",
)
@click.option(
    "--epochs",
    type=int,
    default=2000,
    help="Optimization epochs (default: 2000).",
)
@click.option(
    "--auto-group/--no-auto-group",
    default=False,
    help="Enable automatic functional grouping (default: disabled).",
)
def benchmark(
    pcbs: str,
    output: Optional[Path],
    format: str,
    epochs: int,
    auto_group: bool,
) -> None:
    """
    Run placement benchmarks against human baselines.

    Compares the optimizer's placement quality (wirelength, overlap, etc.)
    against production-quality human designs.

    Example:
        temper-placer benchmark --pcbs piantor_left,bitaxe_ultra
    """
    from temper_placer.report.generator import (
        BenchmarkSummary,
        BenchmarkResult,
        calculate_benchmark_result,
        generate_text_report,
        generate_json_report,
    )
    from temper_placer.io.reference_loader import list_reference_designs, load_reference_pcb
    from temper_placer.optimizer import train, OptimizerConfig
    from temper_placer.io.config_loader import load_constraints, create_board_from_constraints
    from temper_placer.losses import (
        CompositeLoss,
        WeightedLoss,
        OverlapLoss,
        BoundaryLoss,
        WirelengthLoss,
        SpreadLoss,
        GroupClusterLoss,
        GroupConfig,
    )
    from temper_placer.losses.base import LossContext
    from temper_placer.core.community import detect_communities
    import jax.numpy as jnp

    console.print(Panel.fit(
        "[bold blue]temper-placer benchmark[/]\nComparing optimizer to human ground truth",
        border_style="blue",
    ))

    # 1. Identify PCBs
    design_dir = Path("tests/fixtures/external/.cache")
    all_designs = []
    seen_names = set()
    
    if design_dir.exists():
        for p in design_dir.iterdir():
            if p.is_dir() and p.name not in seen_names:
                for pcb in p.glob("*.kicad_pcb"):
                    all_designs.append({
                        "name": p.name,
                        "path": str(pcb)
                    })
                    seen_names.add(p.name)
                    break # Only one PCB per project for now
    
    selected_names = [] if pcbs == "all" else [n.strip() for n in pcbs.split(",")]
    targets = []
    for d in all_designs:
        if pcbs == "all" or d["name"] in selected_names:
            targets.append(d)

    if not targets:
        console.print(f"[red]No matching PCBs found in {design_dir}[/]")
        return

    console.print(f"Found {len(targets)} benchmark targets.\n")

    # 2. Setup Loss Factory
    def make_benchmark_loss(weights, netlist=None, detected_communities=None):
        losses = []
        losses.append(WeightedLoss(OverlapLoss(margin=1.0, rotation_invariant=True), weight=weights["overlap"]))
        losses.append(WeightedLoss(BoundaryLoss(), weight=weights["boundary"]))
        losses.append(WeightedLoss(WirelengthLoss(), weight=weights["wirelength"]))
        losses.append(WeightedLoss(SpreadLoss(), weight=weights["spread"]))

        if auto_group and detected_communities and netlist:
            group_configs = []
            for comm in detected_communities:
                indices = [netlist.get_component_index(ref) for ref in comm.component_refs]
                group_configs.append(
                    GroupConfig(
                        name=comm.name,
                        component_indices=jnp.array(indices, dtype=jnp.int32),
                        max_diameter_mm=30.0,
                        weight=1.0,
                    )
                )
            losses.append(WeightedLoss(GroupClusterLoss(group_configs), weight=10.0))

        return CompositeLoss(losses)

    default_weights = {"overlap": 100.0, "boundary": 50.0, "wirelength": 10.0, "spread": 5.0}

    # 3. Run Benchmarks
    summary = BenchmarkSummary(total_pcbs=len(targets), passed=0, failed=0, better_than_human=0)
    
    for target in targets:
        name = target["name"]
        pcb_path = Path(target["path"])
        console.print(f"Benchmarking [cyan]{name}[/]...")
        
        try:
            # 1. Load Human Baseline
            baseline_path = pcb_path.parent / f"{name}_benchmark.yaml"
            if not baseline_path.exists():
                # Try legacy name just in case
                legacy_path = pcb_path.parent / f"{name}_baseline.yaml"
                if legacy_path.exists():
                    baseline_path = legacy_path
                else:
                    console.print(f"  [yellow]Warning:[/] Benchmark baseline not found for {name}. Run generate_unrouted_benchmarks.py first.")
                    continue
                
            with open(baseline_path) as f:
                import yaml as yaml_module
                baseline = yaml_module.safe_load(f)
            
            # 2. Setup Optimizer Data
            ref_design = load_reference_pcb(pcb_path)
            
            # Load constraints
            config_path = pcb_path.parent / f"{name}_constraints.yaml"
            if config_path.exists():
                constraints = load_constraints(config_path)
            else:
                from temper_placer.io.config_loader import PlacementConstraints
                constraints = PlacementConstraints()
            
            board = create_board_from_constraints(constraints)
            context = LossContext.from_netlist_and_board(ref_design.netlist, board)
            
            # Community detection for auto-grouping
            detected = []
            if auto_group:
                detected = detect_communities(ref_design.netlist)

            # Create loss for this specific board
            composite_loss = make_benchmark_loss(default_weights, ref_design.netlist, detected)

            # 3. Run Optimizer
            cfg = OptimizerConfig(epochs=epochs, seed=42, log_interval=max(1, epochs//10))
            opt_result = train(ref_design.netlist, board, composite_loss, context, cfg)
            
            # 4. Compute Real Score
            res = calculate_benchmark_result(name, opt_result, baseline, context)
            
            summary.results.append(res)
            if res.status == "FAIL":
                summary.failed += 1
            else:
                summary.passed += 1
                if res.status == "BETTER":
                    summary.better_than_human += 1
            
            console.print(f"  [green]✓[/] Result: {res.status} (WL: {res.wirelength_ratio:.2f}x)")
            
        except Exception as e:
            console.print(f"  [red]Failed to benchmark {name}: {e}[/]")
            summary.failed += 1
            import traceback
            console.print(traceback.format_exc())

    # 4. Generate Report
    if format == "text":
        report_text = generate_text_report(summary)
        if output:
            output.write_text(report_text)
            console.print(f"\n[green]✓[/] Report written to {output}")
        else:
            print(report_text)
    else:
        if output:
            generate_json_report(summary, output)
            console.print(f"\n[green]✓[/] JSON report written to {output}")
        else:
            console.print(json.dumps(summary.to_dict(), indent=2))


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
@click.argument("input_pcb", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="Output HTML file path. If not specified, opens in browser.",
)
@click.option(
    "--title",
    type=str,
    default=None,
    help="Title for the visualization.",
)
@click.option(
    "--no-refs/--refs",
    default=False,
    help="Hide component reference designators.",
)
@click.option(
    "--no-zones/--zones",
    default=False,
    help="Hide board zones.",
)
@click.option(
    "--show-traces/--no-traces",
    default=True,
    help="Show/hide copper traces (default: show).",
)
@click.option(
    "--show-pads/--no-pads",
    default=True,
    help="Show/hide component pads (default: show).",
)
@click.option(
    "--debug",
    is_flag=True,
    default=False,
    help="Print coordinate debug info to console.",
)
@click.option(
    "--grid/--no-grid",
    default=True,
    help="Show/hide coordinate grid (default: show).",
)
@click.option(
    "--width",
    type=int,
    default=1000,
    help="Figure width in pixels.",
)
@click.option(
    "--height",
    type=int,
    default=800,
    help="Figure height in pixels.",
)
@click.option(
    "--export-coords",
    type=click.Path(path_type=Path),
    default=None,
    help="Export coordinates to CSV file for external comparison.",
)
def visualize(
    input_pcb: Path,
    output: Optional[Path],
    title: Optional[str],
    no_refs: bool,
    no_zones: bool,
    show_traces: bool,
    show_pads: bool,
    debug: bool,
    grid: bool,
    width: int,
    height: int,
    export_coords: Optional[Path],
) -> None:
    """
    Visualize a KiCad PCB file in the browser.

    Generates an interactive HTML visualization of the PCB layout with
    component positions, zones, traces, pads, and hover information.

    Example:
        temper-placer visualize temper.kicad_pcb
        temper-placer visualize temper.kicad_pcb -o board.html
        temper-placer visualize temper.kicad_pcb --debug --no-traces
        temper-placer visualize temper.kicad_pcb --export-coords coords.csv
    """
    console.print(f"[bold blue]Visualizing:[/] {input_pcb}")

    try:
        from temper_placer.io.kicad_parser import parse_kicad_pcb
        from temper_placer.visualization.model import (
            BoardView,
            ComponentView,
            PadView,
            Point,
            TraceView,
            ZoneView,
        )
        from temper_placer.visualization.board_renderer import board_to_html
    except ImportError as e:
        console.print(f"[red]Failed to import required modules: {e}[/]")
        sys.exit(1)

    # Step 1: Parse PCB
    console.print("[dim]Parsing PCB file...[/]")
    try:
        result = parse_kicad_pcb(input_pcb)
        netlist = result.netlist
        board_geom = result.board

        if result.has_warnings:
            for w in result.warnings:
                console.print(f"  [yellow]Warning:[/] {w}")

        console.print(
            f"  [green]✓[/] Loaded {netlist.n_components} components, {netlist.n_nets} nets"
        )
    except Exception as e:
        console.print(f"[red]Failed to parse PCB: {e}[/]")
        sys.exit(1)

    # Step 2: Convert to BoardView
    console.print("[dim]Creating visualization...[/]")

    # Get board origin for coordinate transformation
    board_width = board_geom.width if board_geom else 100.0
    board_height = board_geom.height if board_geom else 100.0
    origin_x, origin_y = board_geom.origin if board_geom else (0.0, 0.0)

    # Convert components to ComponentView (transform to board-relative coords)
    component_views = []
    for comp in netlist.components:
        # Get position (use initial_position or default to (0, 0))
        pos = comp.initial_position or (0.0, 0.0)
        # Transform to board-relative coordinates
        rel_x = pos[0] - origin_x
        rel_y = pos[1] - origin_y
        # Get rotation in degrees (initial_rotation is 0-3 index for 0/90/180/270)
        rot_deg = (comp.initial_rotation or 0) * 90.0
        # Get component value from attributes
        value = comp.attributes.get("Value") if comp.attributes else None

        component_views.append(
            ComponentView(
                ref=comp.ref,
                position=Point(rel_x, rel_y),
                rotation=rot_deg,
                width=comp.bounds[0],
                height=comp.bounds[1],
                footprint=comp.footprint,
                value=value,
            )
        )

    # Convert zones to ZoneView (if available)
    zone_views = []
    if board_geom and board_geom.zones:
        for zone in board_geom.zones:
            # Zone uses bounds (x_min, y_min, x_max, y_max), convert to polygon
            # Transform to board-relative coordinates
            x_min, y_min, x_max, y_max = zone.bounds
            polygon_points = (
                Point(x_min - origin_x, y_min - origin_y),
                Point(x_max - origin_x, y_min - origin_y),
                Point(x_max - origin_x, y_max - origin_y),
                Point(x_min - origin_x, y_max - origin_y),
            )
            zone_views.append(
                ZoneView(
                    name=zone.name,
                    polygon=polygon_points,
                    zone_type="generic",
                )
            )

    # Convert traces to TraceView (transform to board-relative coords)
    trace_views = []
    for t in result.traces:
        trace_views.append(
            TraceView(
                start=Point(t.start[0] - origin_x, t.start[1] - origin_y),
                end=Point(t.end[0] - origin_x, t.end[1] - origin_y),
                width=t.width,
                layer=t.layer,
                net=t.net,
            )
        )

    # Convert pads to PadView (transform to board-relative coords)
    pad_views = []
    for p in result.pads:
        pad_views.append(
            PadView(
                position=Point(p.position[0] - origin_x, p.position[1] - origin_y),
                size=p.size,
                shape=p.shape,
                rotation=p.rotation,
                layer=p.layer,
                number=p.number,
                net=p.net,
                component_ref=p.component_ref,
            )
        )

    board_view = BoardView(
        width=board_width,
        height=board_height,
        components=tuple(component_views),
        zones=tuple(zone_views),
        traces=tuple(trace_views),
        pads=tuple(pad_views),
        title=title or input_pcb.stem,
    )

    console.print(f"  [green]✓[/] Board: {board_width:.1f}mm x {board_height:.1f}mm")
    console.print(f"  [green]✓[/] Components: {len(component_views)}")
    console.print(f"  [green]✓[/] Traces: {len(trace_views)}")
    console.print(f"  [green]✓[/] Pads: {len(pad_views)}")
    console.print(f"  [green]✓[/] Zones: {len(zone_views)}")

    # Debug output (optional)
    if debug:
        console.print(f"\n[bold]Debug Info:[/]")
        console.print(
            f"Board: {board_width:.1f} x {board_height:.1f} mm, "
            f"origin=({origin_x:.1f}, {origin_y:.1f})"
        )
        console.print(f"Components ({len(component_views)}):")
        for cv in component_views[:10]:  # Show first 10
            console.print(
                f"  {cv.ref}: ({cv.position.x:.1f}, {cv.position.y:.1f}) rel, "
                f"({cv.position.x + origin_x:.1f}, {cv.position.y + origin_y:.1f}) abs, "
                f"{cv.rotation:.0f}°, {cv.width:.1f}x{cv.height:.1f}mm"
            )
        if len(component_views) > 10:
            console.print(f"  ... and {len(component_views) - 10} more")
        console.print(f"Traces: {len(trace_views)} segments")
        console.print(f"Pads: {len(pad_views)} total")
        console.print("")

    # Export coordinates to CSV (optional)
    if export_coords:
        from temper_placer.visualization.validation import export_coordinates_csv

        csv_content = export_coordinates_csv(
            board_view,
            origin=(origin_x, origin_y),
            output_path=export_coords,
        )
        console.print(f"[green]✓[/] Exported coordinates to {export_coords}")

    # Step 3: Generate HTML
    console.print("[dim]Generating HTML...[/]")

    try:
        html_content = board_to_html(
            board_view,
            show_refs=not no_refs,
            show_zones=not no_zones,
            show_traces=show_traces,
            show_pads=show_pads,
            show_grid=grid,
            width=width,
            height=height,
        )
    except ImportError:
        console.print("[red]Plotly is required for visualization.[/]")
        console.print("Install with: pip install plotly>=5.18.0")
        sys.exit(1)

    # Step 4: Output
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(html_content)
        console.print(f"[green]✓[/] Wrote {output}")
    else:
        # Write to temp file and open in browser
        import tempfile
        import webbrowser

        with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
            f.write(html_content)
            temp_path = f.name

        console.print(f"[green]✓[/] Opening in browser...")
        webbrowser.open(f"file://{temp_path}")

    console.print("[bold green]Done![/]")


@main.command()
@click.argument("input_pcb", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    required=True,
    help="Output HTML report file path.",
)
@click.option(
    "--loss-history",
    type=click.Path(exists=True, path_type=Path),
    help="Optional loss history JSON file from optimization.",
)
@click.option(
    "--title",
    type=str,
    default="Placement Optimization Report",
    help="Report title.",
)
@click.option(
    "--no-board/--board",
    default=False,
    help="Exclude board visualization section.",
)
@click.option(
    "--no-components/--components",
    default=False,
    help="Exclude component table section.",
)
@click.option(
    "--drc/--no-drc",
    default=False,
    help="Run KiCad DRC validation and include results (requires kicad-cli).",
)
def report(
    input_pcb: Path,
    output: Path,
    loss_history: Optional[Path],
    title: str,
    no_board: bool,
    no_components: bool,
    drc: bool,
) -> None:
    """
    Generate an HTML report for a placed PCB.

    Creates a comprehensive report including board visualization,
    component placements, and optionally loss curves from optimization.

    Example:
        temper-placer report optimized.kicad_pcb -o report.html
        temper-placer report optimized.kicad_pcb -o report.html --loss-history losses.json
        temper-placer report optimized.kicad_pcb -o report.html --drc
    """
    console.print(f"[bold blue]Generating report:[/] {input_pcb}")

    try:
        from temper_placer.io.kicad_parser import parse_kicad_pcb
        from temper_placer.visualization.model import (
            BoardView,
            ComponentView,
            LossHistory,
            LossDataPoint,
            Point,
            ZoneView,
        )
        from temper_placer.visualization.report import generate_report, ReportConfig
    except ImportError as e:
        console.print(f"[red]Failed to import required modules: {e}[/]")
        sys.exit(1)

    # Step 1: Parse PCB
    console.print("[dim]Parsing PCB file...[/]")
    try:
        result = parse_kicad_pcb(input_pcb)
        netlist = result.netlist
        board_geom = result.board

        if result.has_warnings:
            for w in result.warnings:
                console.print(f"  [yellow]Warning:[/] {w}")

        console.print(
            f"  [green]✓[/] Loaded {netlist.n_components} components, {netlist.n_nets} nets"
        )
    except Exception as e:
        console.print(f"[red]Failed to parse PCB: {e}[/]")
        sys.exit(1)

    # Step 2: Convert to BoardView
    console.print("[dim]Creating board view...[/]")

    # Get board origin for coordinate transformation
    board_width = board_geom.width if board_geom else 100.0
    board_height = board_geom.height if board_geom else 100.0
    origin_x, origin_y = board_geom.origin if board_geom else (0.0, 0.0)

    component_views = []
    for comp in netlist.components:
        pos = comp.initial_position or (0.0, 0.0)
        # Transform to board-relative coordinates
        rel_x = pos[0] - origin_x
        rel_y = pos[1] - origin_y
        rot_deg = (comp.initial_rotation or 0) * 90.0

        component_views.append(
            ComponentView(
                ref=comp.ref,
                position=Point(rel_x, rel_y),
                rotation=rot_deg,
                width=comp.bounds[0],
                height=comp.bounds[1],
                footprint=comp.footprint,
            )
        )

    zone_views = []
    if board_geom and board_geom.zones:
        for zone in board_geom.zones:
            x_min, y_min, x_max, y_max = zone.bounds
            polygon_points = (
                Point(x_min - origin_x, y_min - origin_y),
                Point(x_max - origin_x, y_min - origin_y),
                Point(x_max - origin_x, y_max - origin_y),
                Point(x_min - origin_x, y_max - origin_y),
            )
            zone_views.append(
                ZoneView(
                    name=zone.name,
                    polygon=polygon_points,
                    zone_type="generic",
                )
            )

    board_view = BoardView(
        width=board_width,
        height=board_height,
        components=tuple(component_views),
        zones=tuple(zone_views),
        title=input_pcb.stem,
    )

    console.print(f"  [green]✓[/] Board: {board_width:.1f}mm x {board_height:.1f}mm")
    console.print(f"  [green]✓[/] Components: {len(component_views)}")

    # Step 3: Load loss history if provided
    loss_hist = None
    if loss_history:
        console.print("[dim]Loading loss history...[/]")
        try:
            with open(loss_history, "r") as f:
                loss_data = json.load(f)

            loss_hist = LossHistory()
            for dp in loss_data.get("data_points", []):
                loss_hist.add_point(
                    LossDataPoint(
                        epoch=dp.get("epoch", 0),
                        total_loss=dp.get("total_loss", 0.0),
                        breakdown=dp.get("breakdown", {}),
                        temperature=dp.get("temperature"),
                        learning_rate=dp.get("learning_rate"),
                    )
                )
            loss_hist.phase_boundaries = loss_data.get("phase_boundaries", [])
            loss_hist.phase_names = loss_data.get("phase_names", [])

            console.print(f"  [green]✓[/] Loaded {len(loss_hist.data_points)} data points")
        except Exception as e:
            console.print(f"  [yellow]Warning:[/] Failed to load loss history: {e}")

    # Step 4: Run DRC if requested
    validation_results = None
    if drc:
        console.print("[dim]Running KiCad DRC validation...[/]")
        try:
            from temper_placer.validation.drc import KiCadDRCValidator
            from temper_placer.visualization.report import ValidationResults

            drc_validator = KiCadDRCValidator()
            if drc_validator.is_available():
                drc_result = drc_validator.run_drc(input_pcb)

                # Convert DRC result to ValidationResults for report
                drc_errors = []
                drc_warnings = []
                for violation in drc_result.violations:
                    msg = violation.message or f"{violation.violation_type.value} violation"
                    if violation.position:
                        msg += f" at ({violation.position[0]:.2f}, {violation.position[1]:.2f})mm"
                    if violation.affected_items:
                        msg += f" - {', '.join(violation.affected_items)}"

                    if violation.severity.name == "ERROR":
                        drc_errors.append(msg)
                    else:
                        drc_warnings.append(msg)

                validation_results = ValidationResults(
                    drc_passed=not drc_result.has_errors,
                    drc_errors=drc_errors,
                    drc_warnings=drc_warnings,
                )

                status_icon = "[green]✓[/]" if not drc_result.has_errors else "[red]✗[/]"
                console.print(
                    f"  {status_icon} DRC: {drc_result.error_count} errors, "
                    f"{drc_result.warning_count} warnings ({drc_result.elapsed_ms:.0f}ms)"
                )
            else:
                console.print("  [yellow]Warning:[/] kicad-cli not available - skipping DRC")
        except Exception as e:
            console.print(f"  [yellow]Warning:[/] DRC validation failed: {e}")

    # Step 5: Generate report
    console.print("[dim]Generating report...[/]")

    config = ReportConfig(
        title=title,
        include_board_view=not no_board,
        include_component_table=not no_components,
        include_loss_curves=loss_hist is not None,
        include_validation_results=validation_results is not None,
    )

    try:
        report_html = generate_report(
            board_view=board_view,
            loss_history=loss_hist,
            validation=validation_results,
            config=config,
            output_path=str(output),
        )

        console.print(f"[green]✓[/] Wrote {output}")

    except ImportError:
        console.print("[red]Plotly is required for report generation.[/]")
        console.print("Install with: pip install plotly>=5.18.0")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Failed to generate report: {e}[/]")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    console.print("[bold green]Done![/]")


@main.group()
def ablate() -> None:
    """Run and analyze ablation studies."""
    pass


@ablate.command()
@click.argument("config_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--resume/--no-resume",
    default=True,
    help="Resume from checkpoint if available.",
)
@click.option(
    "--retry-failed",
    is_flag=True,
    help="Retry previously failed experiment runs.",
)
@click.option(
    "--parallel",
    type=int,
    help="Override number of parallel workers.",
)
@click.option(
    "--no-report",
    is_flag=True,
    help="Do not generate HTML report after completion.",
)
def run(
    config_file: Path,
    resume: bool,
    retry_failed: bool,
    parallel: Optional[int],
    no_report: bool,
) -> None:
    """
    Run an ablation study defined in CONFIG_FILE.

    Executes multiple optimization runs with different components enabled/disabled
    to analyze their impact on placement quality.
    """
    console.print(Panel.fit(
        "[bold blue]temper-placer ablate run[/]\nExecuting ablation study pipeline",
        border_style="blue",
    ))

    try:
        from temper_placer.ablation.config import AblationStudyConfig
        from temper_placer.ablation.runner import ExperimentRunner
        from temper_placer.ablation.metrics import MetricAggregator
        from temper_placer.ablation.analysis import AblationAnalyzer
        from temper_placer.ablation.report import AblationReportGenerator

        # Load config
        console.print(f"[dim]Loading study config from {config_file}...[/]")
        study_cfg = AblationStudyConfig.load(config_file)
        
        if parallel:
            study_cfg.parallel_workers = parallel
            
        console.print(f"  [green]✓[/] Study: {study_cfg.study_name}")
        console.print(f"  [green]✓[/] Experiments: {len(study_cfg.experiments)}")
        console.print(f"  [green]✓[/] Seeds: {len(study_cfg.seeds)}")
        console.print(f"  [green]✓[/] Test Cases: {len(study_cfg.test_cases)}")
        console.print(f"  [green]✓[/] Total Runs: {study_cfg.get_total_runs()}")

        # Initialize runner
        runner = ExperimentRunner(study_cfg)
        
        # Run experiments
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            total_task = progress.add_task("Total Progress", total=study_cfg.get_total_runs())
            
            def update_progress(completed, total):
                progress.update(total_task, completed=completed)

            results = runner.run_all(
                resume=resume, 
                retry_failed=retry_failed,
                progress_callback=update_progress
            )

        if not results:
            console.print("[yellow]No results generated.[/]")
            return

        # Analyze and Report
        if not no_report:
            console.print("\n[bold cyan]Generating Analysis and Report...[/]")
            
            aggregator = MetricAggregator()
            aggregated = aggregator.aggregate(results)
            
            analyzer = AblationAnalyzer(aggregated)
            
            report_gen = AblationReportGenerator(study_cfg.output_dir)
            report_path = report_gen.generate(study_cfg.study_name, aggregated, analyzer)
            
            console.print(f"  [green]✓[/] Report saved to: {report_path}")
            
    except Exception as e:
        console.print(f"[red]Ablation study failed: {e}[/]")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    console.print("\n[bold green]Ablation study complete![/]")


@ablate.command()
@click.argument("results_dir", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--name",
    type=str,
    default="Ablation Analysis",
    help="Name for the study in the report.",
)
def report(
    results_dir: Path,
    name: str,
) -> None:
    """
    Generate an HTML report from existing ablation results.
    """
    console.print(f"[bold blue]Generating Ablation Report for:[/] {results_dir}")

    try:
        import pickle
        from temper_placer.ablation.metrics import MetricAggregator
        from temper_placer.ablation.analysis import AblationAnalyzer
        from temper_placer.ablation.report import AblationReportGenerator

        checkpoint_path = results_dir / "checkpoint.pkl"
        if not checkpoint_path.exists():
            console.print(f"[red]Results checkpoint not found at {checkpoint_path}[/]")
            sys.exit(1)

        with open(checkpoint_path, "rb") as f:
            checkpoint = pickle.load(f)
            
        results = checkpoint.results
        console.print(f"  [green]✓[/] Loaded {len(results)} experiment runs")

        aggregator = MetricAggregator()
        aggregated = aggregator.aggregate(results)
        
        analyzer = AblationAnalyzer(aggregated)
        
        report_gen = AblationReportGenerator(results_dir)
        report_path = report_gen.generate(name, aggregated, analyzer)
        
        console.print(f"  [green]✓[/] Report saved to: {report_path}")
        
    except Exception as e:
        console.print(f"[red]Report generation failed: {e}[/]")
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
