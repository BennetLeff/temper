"""temper-placer CLI dispatcher — discovers subcommands via entry_points."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table

from temper_placer import __version__
from temper_placer.profiling.cli import profile

from ._io import _print_placement_summary, console
from ._signal import InterruptGuard
from .andon_commands import andon
from .dsn_commands import dsn
from .pipeline_commands import phase, pipeline
from .timing import timing
from .trace_commands import trace
from .version import version
from .watch_commands import watch


@click.group()
@click.version_option(version=__version__, prog_name="temper-placer")
def main() -> None:
    """temper-placer: CP-SAT-based PCB placement optimizer."""
    pass


main.add_command(pipeline)
main.add_command(phase)
main.add_command(trace)
main.add_command(dsn)
main.add_command(andon)
main.add_command(timing)
main.add_command(profile)
main.add_command(watch)

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
    "--weight-overlap",
    type=float,
    default=None,
    help="Override overlap loss weight.",
)
@click.option(
    "--weight-wirelength",
    type=float,
    default=None,
    help="Override wirelength loss weight.",
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
@click.option(
    "--loss-history",
    type=click.Path(path_type=Path),
    help="Save full loss history to JSON file.",
)
@click.option(
    "--log-all-epochs",
    is_flag=True,
    default=False,
    help="Record metrics for every epoch (warning: increases file size).",
)
@click.option(
    "--verbose-losses",
    is_flag=True,
    default=False,
    help="Show detailed loss breakdown in console during optimization.",
)
@click.option(
    "--parallel-seeds",
    type=int,
    default=1,
    help="Number of random seeds to run in parallel (default: 1).",
)
@click.option(
    "--multi-seed",
    is_flag=True,
    default=False,
    help="Enable DPP-diversified multi-seed placement with triage gate.",
)
@click.option(
    "--init-method",
    type=click.Choice(
        ["random", "spectral", "zone_aware_spectral", "constraint_weighted_spectral", "learned"]
    ),
    default=None,
    help="Initialization method (default: constraint_weighted_spectral).",
)
@click.option(
    "--ccap/--no-ccap",
    default=None,
    help="Enable/disable C-CAP feasibility pre-projection (default: enabled).",
)
@click.option(
    "--precluster/--no-precluster",
    default=None,
    help="Enable/disable hierarchical group pre-clustering (default: enabled).",
)
@click.option(
    "--skip-topological",
    is_flag=True,
    default=False,
    help="Skip topological initialization heuristic (default: enabled).",
)
@click.option(
    "--track-metrics",
    type=click.Path(path_type=Path),
    help="Enable metrics tracking, save to this directory.",
)
@click.option(
    "--spice-validate/--no-spice-validate",
    default=False,
    help="Run SPICE simulation for electrical validation after optimization.",
)
@click.option(
    "--spice-penalty-weight",
    type=float,
    default=100.0,
    help="Weight for SPICE validation penalty in loss function (if enabled).",
)
@click.option(
    "--weight-channel-capacity",
    type=float,
    default=None,
    help="Override channel capacity loss weight.",
)
@click.option(
    "--compact/--no-compact",
    default=False,
    help="Use the consolidated Core 8 loss set (default: False).",
)
@click.option(
    "--placer",
    type=click.Choice(["jax-deprecated"]),
    default=None,
    help="Deprecated: JAX placement engine has been removed. Use CP-SAT (default).",
)
@click.option(
    "--cp-sat-timeout",
    type=int,
    default=300,
    help="CP-SAT solver timeout in seconds (default: 300).",
)
@click.option(
    "--cp-sat-workers",
    type=int,
    default=8,
    help="CP-SAT solver search workers (default: 8).",
)
@click.option(
    "--cp-sat-grid-scale",
    type=int,
    default=10,
    help="CP-SAT grid scale in units per mm (default: 10 = 0.1mm).",
)
def optimize(
    input_pcb: Path,
    config: Path,
    output: Path,
    epochs: int,
    weight_overlap: float | None,
    weight_wirelength: float | None,
    visualize: bool,
    port: int,
    seed: int,
    checkpoint: Path | None,
    curriculum: bool,
    placements_json: Path | None,
    heuristics: bool,
    auto_group: bool,
    centrality: bool,
    profile_dir: Path | None,
    grad_norm: bool,
    grad_norm_alpha: float,
    grad_norm_lr: float,
    loss_history: Path | None,
    log_all_epochs: bool,
    verbose_losses: bool,
    parallel_seeds: int,
    multi_seed: bool,
    init_method: str | None,
    ccap: bool | None,
    precluster: bool | None,
    skip_topological: bool,
    track_metrics: Path | None,
    spice_validate: bool,
    spice_penalty_weight: float,
    weight_channel_capacity: float | None,
    compact: bool,
    placer: str | None,
    cp_sat_timeout: int,
    cp_sat_workers: int,
    cp_sat_grid_scale: int,
) -> None:
    """
    Optimize component placement for a KiCad PCB.

    Reads INPUT_PCB and constraint CONFIG, runs CP-SAT optimization,
    and writes the result to OUTPUT.

    Examples:
        temper-placer optimize temper.kicad_pcb -c constraints.yaml -o optimized.kicad_pcb
    """
    # Handle deprecated --placer jax-deprecated flag
    if placer == "jax-deprecated":
        console.print(
            "[red]ERROR:[/] --placer jax-deprecated is no longer supported.\n"
            "  The JAX optimizer stack has been removed (see plan 2026-07-03-002).\n"
            "  CP-SAT is now the default and only placement engine.\n"
            "  Remove the --placer flag from your invocation."
        )
        sys.exit(1)

    console.print(
        Panel.fit(
            f"[bold blue]temper-placer[/] v{__version__}\nCP-SAT-based PCB placement optimizer",
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
    console.print(f"[bold]Loss Set:[/] {'[bold cyan]Compact (Core 8)[/]' if compact else 'Standard (Legacy)'}")
    console.print(f"[bold]Placer:[/] {placer}")

    # ------------------------------------------------------------------
    # CP-SAT placer dispatch (default — no --placer flag needed)
    # ------------------------------------------------------------------
    console.print(f"\n[bold green]Using CP-SAT placer[/]")
    console.print(f"  [dim]timeout={cp_sat_timeout}s, workers={cp_sat_workers}, grid_scale={cp_sat_grid_scale}[/]")

    # Import CP-SAT modules (with ortools availability guard)
    try:
        from temper_placer.placer.cp_sat import (
            SolveStatus,
            build_cp_sat_model,
            solve_cp_sat_model,
        )
        from temper_placer.placer.cp_sat.audit import audit_placement
    except ImportError as e:
        console.print(f"[red]CP-SAT placer unavailable: {e}[/]")
        console.print("Ensure ortools is installed: pip install ortools")
        sys.exit(1)

    # Import parsing modules (non-JAX path — same functions as JAX path)
    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.io.config_loader import (
        create_board_from_constraints,
        load_constraints,
    )

    # Step 1: Parse KiCad PCB
    console.print("\n[bold cyan]Step 1/4:[/] Parsing KiCad PCB...")
    try:
        parse_result = parse_kicad_pcb(input_pcb)
        netlist = parse_result.netlist
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
    console.print("\n[bold cyan]Step 2/4:[/] Loading constraints...")
    try:
        constraints_obj = load_constraints(config)
        board = create_board_from_constraints(constraints_obj)
        console.print(f"  [green]✓[/] Board: {board.width:.1f}mm x {board.height:.1f}mm")
    except Exception as e:
        console.print(f"[red]Failed to load constraints: {e}[/]")
        sys.exit(1)

    # Build component dict for CP-SAT model
    components_dict: dict[str, dict] = {}
    for comp in netlist.components:
        components_dict[comp.ref] = {
            "width_mm": comp.width,
            "height_mm": comp.height,
        }

    # Step 3: Build CP-SAT model (NoOverlap2D + side constraints)
    console.print("\n[bold cyan]Step 3/4:[/] Building CP-SAT model...")
    model, ctx = build_cp_sat_model(
        components=components_dict,
        board_w_mm=board.width,
        board_h_mm=board.height,
        scale_factor=cp_sat_grid_scale,
    )
    console.print(f"  [green]✓[/] Model built: {len(components_dict)} components")

    # Try PCL constraint encoding (U3); skip if encoder not available
    try:
        from temper_placer.placer.cp_sat.encoder import compile_pcl_to_cp_sat
        if hasattr(constraints_obj, "pcl_constraints") and constraints_obj.pcl_constraints:
            console.print("  [dim]PCL constraint encoding (U3) not yet integrated — skipping[/]")
    except ImportError:
        pass  # U3 encoder not yet available

    # Step 4: Solve
    console.print(f"\n[bold cyan]Step 4/4:[/] Solving CP-SAT model...")
    console.print(f"  [dim]timeout={cp_sat_timeout}s, workers={cp_sat_workers}[/]")

    result = solve_cp_sat_model(
        model,
        ctx,
        timeout_s=cp_sat_timeout,
        num_workers=cp_sat_workers,
    )

    console.print(f"  Status: [bold]{result.status.value}[/]")
    console.print(f"  Solve time: {result.solve_time_s:.1f}s")
    if result.objective_value is not None:
        console.print(f"  Objective: {result.objective_value:.1f}")

    if result.status in (SolveStatus.OPTIMAL, SolveStatus.FEASIBLE):
        # Audit placement (U4)
        console.print("\n[bold cyan]Auditing placement...[/]")
        audit_result = audit_placement(
            positions=result.positions,
            components=components_dict,
            constraints=None,
            board_w_mm=board.width,
            board_h_mm=board.height,
        )

        passed = audit_result.stats["passed"]
        checked = audit_result.stats["checked"]
        failed = audit_result.stats["failed"]
        if audit_result.passed:
            console.print(f"  [green]✓[/] Audit passed: {passed}/{checked} checks OK")
        else:
            console.print(f"  [red]✗[/] Audit failed: {failed} violation(s)")
            for v in audit_result.violations[:10]:
                console.print(f"    [red]- {v.detail}[/]")

        # Print positions summary
        console.print(f"\n[bold]Placement ({len(result.positions)} components):[/]")
        for i, (ref, (x, y)) in enumerate(sorted(result.positions.items())):
            if i >= 10:
                console.print(f"  ... and {len(result.positions) - 10} more")
                break
            w = components_dict[ref]["width_mm"]
            h = components_dict[ref]["height_mm"]
            console.print(f"  {ref:12s}  ({x:7.1f}, {y:7.1f})  [{w:.1f}x{h:.1f}mm]")

        # Check for infeasibility due to constraints (U7 not yet wired)
        if not audit_result.passed:
            console.print("\n[yellow]Placement has constraint violations — review the audit output above.[/]")

    elif result.status == SolveStatus.INFEASIBLE:
        console.print("[red]No feasible placement found (INFEASIBLE).[/]")
        console.print("  [dim]UNSAT core extraction (U7) not yet implemented[/]")
        sys.exit(1)
    else:
        console.print(f"[yellow]Solver returned {result.status.value} (timeout or unknown).[/]")
        console.print("  Try increasing --cp-sat-timeout or check constraints.")
        sys.exit(1)

    console.print("\n[bold green]CP-SAT placement complete![/]")
    return

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
        with open(placements) as f:
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
    config: Path | None,
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
        PreflightResult,
        check_components_have_zones,
        check_external_tools,
        check_impossible_constraints,
        check_zones_fit_on_board,
    )

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
            console.print("[bold red]✗ Validation failed[/]")
        console.print(
            f"  {result.error_count} errors, {result.warning_count} warnings, {result.info_count} info"
        )

    # Exit code
    if strict:
        sys.exit(0 if result.passed and result.warning_count == 0 else 1)
    else:
        sys.exit(0 if result.passed else 1)



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
    output: Path | None,
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
    import jax.numpy as jnp

    from temper_placer.core.community import detect_communities
    from temper_placer.io.config_loader import create_board_from_constraints, load_constraints
    from temper_placer.io.reference_loader import load_reference_pcb
    from temper_placer.losses import (
        BoundaryLoss,
        CompositeLoss,
        GroupClusterLoss,
        GroupConfig,
        OverlapLoss,
        SpreadLoss,
        WeightedLoss,
        WirelengthLoss,
    )
    try:
        from temper_placer.losses.base import LossContext
        from temper_placer.optimizer import OptimizerConfig, train
    except ImportError:
        pass  # JAX optimizer deleted (plan 2026-07-03-002 U5)
    from temper_placer.report.generator import (
        BenchmarkSummary,
        calculate_benchmark_result,
        generate_json_report,
        generate_text_report,
    )

    console.print(
        Panel.fit(
            "[bold blue]temper-placer benchmark[/]\nComparing optimizer to human ground truth",
            border_style="blue",
        )
    )

    # 1. Identify PCBs
    design_dir = Path("tests/fixtures/external/.cache")
    all_designs = []
    seen_names = set()

    if design_dir.exists():
        for p in design_dir.iterdir():
            if p.is_dir() and p.name not in seen_names:
                for pcb in p.glob("*.kicad_pcb"):
                    all_designs.append({"name": p.name, "path": str(pcb)})
                    seen_names.add(p.name)
                    break  # Only one PCB per project for now

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
        losses.append(
            WeightedLoss(
                OverlapLoss(margin=2.0, rotation_invariant=True, inflation_ramp=0.3),
                weight=weights["overlap"],
            )
        )
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
                    console.print(
                        f"  [yellow]Warning:[/] Benchmark baseline not found for {name}. Run generate_unrouted_benchmarks.py first."
                    )
                    continue

            with open(baseline_path) as f:
                import yaml as yaml_module  # type: ignore[import-untyped]

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
            cfg = OptimizerConfig(epochs=epochs, seed=42, log_interval=max(1, epochs // 10))
            opt_result = train(ref_design.netlist, board, composite_loss, context, cfg, constraints=constraints)

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
            console.print(json.dumps(summary.to_dict(), indent=2))  # type: ignore[attr-defined]


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
            "width": board.width,  # type: ignore[union-attr]
            "height": board.height,  # type: ignore[union-attr]
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
@click.option(
    "-c",
    "--constraints",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Load zones from constraints YAML file.",
)
def visualize(
    input_pcb: Path,
    output: Path | None,
    title: str | None,
    no_refs: bool,
    no_zones: bool,
    show_traces: bool,
    show_pads: bool,
    debug: bool,
    grid: bool,
    width: int,
    height: int,
    export_coords: Path | None,
    constraints: Path | None,
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
        from temper_placer.visualization.board_renderer import board_to_html
        from temper_placer.visualization.model import (
            BoardView,
            ComponentView,
            PadView,
            Point,
            TraceView,
            ZoneView,
        )
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

    # Load zones from constraints file if provided
    if constraints:
        try:
            from temper_placer.io.config_loader import (
                create_board_from_constraints,
                load_constraints,
            )

            constraints_obj = load_constraints(constraints)
            board_with_zones = create_board_from_constraints(constraints_obj)

            # Define zone colors for visualization (rgba format for Plotly)
            zone_colors = {
                "power_zone": "rgba(255, 0, 0, 0.1)",  # Red with 10% opacity
                "driver_zone": "rgba(255, 255, 0, 0.1)",  # Yellow with 10% opacity
                "control_zone": "rgba(0, 0, 255, 0.1)",  # Blue with 10% opacity
                "interface_zone": "rgba(0, 255, 0, 0.1)",  # Green with 10% opacity
            }

            if board_with_zones.zones:
                for zone in board_with_zones.zones:
                    # Zone uses bounds (x_min, y_min, x_max, y_max), convert to polygon
                    # Transform to board-relative coordinates
                    x_min, y_min, x_max, y_max = zone.bounds
                    polygon_points = (
                        Point(x_min - origin_x, y_min - origin_y),
                        Point(x_max - origin_x, y_min - origin_y),
                        Point(x_max - origin_x, y_max - origin_y),
                        Point(x_min - origin_x, y_max - origin_y),
                    )

                    # Get color for this zone, default to gray if not defined
                    zone_color = zone_colors.get(zone.name, "rgba(128, 128, 128, 0.1)")

                    zone_views.append(
                        ZoneView(
                            name=zone.name,
                            polygon=polygon_points,
                            zone_type="placement",
                            color=zone_color,
                        )
                    )
        except Exception as e:
            console.print(f"  [yellow]Warning:[/] Failed to load zones from constraints: {e}")

    # Fall back to zones from PCB file if no constraints provided
    elif board_geom and board_geom.zones:
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
    # Note: p.position is already in absolute world coordinates
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
        console.print("\n[bold]Debug Info:[/]")
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

        export_coordinates_csv(
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

        console.print("[green]✓[/] Opening in browser...")
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
    loss_history: Path | None,
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
            LossDataPoint,
            LossHistory,
            Point,
            ZoneView,
        )
        from temper_placer.visualization.report import ReportConfig, generate_report
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
            with open(loss_history) as f:
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
        generate_report(
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
    parallel: int | None,
    no_report: bool,
) -> None:
    """
    Run an ablation study defined in CONFIG_FILE.

    Executes multiple optimization runs with different components enabled/disabled
    to analyze their impact on placement quality.
    """
    console.print(
        Panel.fit(
            "[bold blue]temper-placer ablate run[/]\nExecuting ablation study pipeline",
            border_style="blue",
        )
    )

    try:
        from temper_placer.ablation.analysis import AblationAnalyzer
        from temper_placer.ablation.config import AblationStudyConfig
        from temper_placer.ablation.metrics import MetricAggregator
        from temper_placer.ablation.report import AblationReportGenerator
        from temper_placer.ablation.runner import ExperimentRunner

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

            def update_progress(completed, _total):
                progress.update(total_task, completed=completed)

            results = runner.run_all(
                resume=resume, retry_failed=retry_failed, progress_callback=update_progress
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


@ablate.command("report")
@click.argument("results_dir", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--name",
    type=str,
    default="Ablation Analysis",
    help="Name for the study in the report.",
)
def ablate_report(
    results_dir: Path,
    name: str,
) -> None:
    """
    Generate an HTML report from existing ablation results.
    """
    console.print(f"[bold blue]Generating Ablation Report for:[/] {results_dir}")

    try:
        import pickle

        from temper_placer.ablation.analysis import AblationAnalyzer
        from temper_placer.ablation.metrics import MetricAggregator
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


@main.group()
def pcl() -> None:
    """Placement Constraint Language (PCL) tools."""
    pass


@pcl.command("validate")
@click.argument("pcl_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--pcb",
    type=click.Path(exists=True, path_type=Path),
    help="Optional PCB file to validate component references against.",
)
@click.option(
    "--schema/--no-schema",
    default=True,
    help="Validate against JSON Schema (default: enabled).",
)
@click.option(
    "--strict",
    is_flag=True,
    default=False,
    help="Treat warnings as errors.",
)
@click.option(
    "--json-output",
    is_flag=True,
    default=False,
    help="Output results as JSON.",
)
def pcl_validate(
    pcl_file: Path,
    pcb: Path | None,
    schema: bool,
    strict: bool,
    json_output: bool,
) -> None:
    """
    Validate a PCL constraint file.

    Checks:
    - YAML syntax
    - JSON Schema compliance (structure, required fields, value ranges)
    - Constraint parsing (type dispatch, unit conversion)
    - Component reference validity (if --pcb provided)

    Examples:
        temper-placer pcl validate constraints.yaml
        temper-placer pcl validate constraints.yaml --pcb temper.kicad_pcb
        temper-placer pcl validate constraints.yaml --strict --json-output
    """
    import json as json_module

    from temper_placer.pcl import PCLParseError, parse_pcl_file

    results: dict = {
        "file": str(pcl_file),
        "passed": True,
        "errors": [],
        "warnings": [],
        "info": [],
        "constraints_count": 0,
    }

    if not json_output:
        console.print(f"[bold blue]Validating PCL:[/] {pcl_file}")

    # Step 1: JSON Schema validation (if enabled)
    if schema:
        if not json_output:
            console.print("\n[bold cyan]JSON Schema Validation:[/]")

        try:
            import jsonschema
            import yaml

            # Load schema
            schema_path = Path(__file__).parent / "../../configs/schemas/pcl.schema.json"
            if not schema_path.exists():
                # Try alternate location
                schema_path = (
                    Path(__file__).parent.parent.parent / "configs/schemas/pcl.schema.json"
                )

            if schema_path.exists():
                with open(schema_path) as f:
                    pcl_schema = json_module.load(f)

                # Load YAML as dict
                with open(pcl_file) as f:
                    pcl_data = yaml.safe_load(f)

                # Validate
                jsonschema.validate(pcl_data, pcl_schema)

                if not json_output:
                    console.print("  [green]✓[/] Schema validation passed")
                results["info"].append("Schema validation passed")
            else:
                if not json_output:
                    console.print(
                        "  [yellow]⚠[/] Schema file not found - skipping schema validation"
                    )
                results["warnings"].append("Schema file not found - skipping schema validation")

        except ImportError:
            if not json_output:
                console.print(
                    "  [yellow]⚠[/] jsonschema not installed - skipping schema validation"
                )
                console.print("    Install with: pip install jsonschema")
            results["warnings"].append("jsonschema not installed - skipping schema validation")

        except jsonschema.ValidationError as e:
            error_msg = f"Schema validation failed: {e.message}"
            if e.path:
                error_msg += f" at {'/'.join(str(p) for p in e.path)}"
            results["errors"].append(error_msg)
            results["passed"] = False

            if not json_output:
                console.print(f"  [red]✗[/] {error_msg}")

        except Exception as e:
            error_msg = f"Schema validation error: {e}"
            results["errors"].append(error_msg)
            results["passed"] = False

            if not json_output:
                console.print(f"  [red]✗[/] {error_msg}")

    # Step 2: PCL Parsing
    if not json_output:
        console.print("\n[bold cyan]PCL Parsing:[/]")

    try:
        collection = parse_pcl_file(pcl_file)
        results["constraints_count"] = len(collection)

        if not json_output:
            console.print(f"  [green]✓[/] Parsed {len(collection)} constraints")

        # Show breakdown by tier
        tier_counts: dict[str, int] = {}
        for c in collection.constraints:
            tier_name = c.tier.name
            tier_counts[tier_name] = tier_counts.get(tier_name, 0) + 1

        if not json_output:
            for tier, count in sorted(tier_counts.items()):
                console.print(f"    - {tier}: {count}")

        results["info"].append(f"Parsed {len(collection)} constraints")
        results["tier_breakdown"] = tier_counts

    except PCLParseError as e:
        error_msg = f"Parse error: {e}"
        results["errors"].append(error_msg)
        results["passed"] = False

        if not json_output:
            console.print(f"  [red]✗[/] {error_msg}")

        # Can't continue without parsed collection
        if json_output:
            print(json_module.dumps(results, indent=2))
        sys.exit(1)

    # Step 3: Component Reference Validation (if PCB provided)
    if pcb:
        if not json_output:
            console.print("\n[bold cyan]Component Reference Validation:[/]")

        try:
            from temper_placer.io.kicad_parser import parse_kicad_pcb

            parse_result = parse_kicad_pcb(pcb)
            component_refs = [c.ref for c in parse_result.netlist.components]

            # Auto-enrich constraints from design data
            collection.auto_enrich(parse_result.netlist, parse_result.board)

            if not json_output:
                console.print(f"  [dim]Loaded {len(component_refs)} components from PCB[/]")

            # Validate references
            ref_errors = collection.validate_component_refs(component_refs)

            if ref_errors:
                for err in ref_errors:
                    results["warnings"].append(err)
                    if not json_output:
                        console.print(f"  [yellow]⚠[/] {err}")

                if strict:
                    results["passed"] = False
            else:
                if not json_output:
                    console.print("  [green]✓[/] All component references valid")
                results["info"].append("All component references valid")

        except Exception as e:
            error_msg = f"PCB validation error: {e}"
            results["errors"].append(error_msg)
            results["passed"] = False

            if not json_output:
                console.print(f"  [red]✗[/] {error_msg}")

    # Step 4: Check 'because' field quality
    if not json_output:
        console.print("\n[bold cyan]Rationale Quality:[/]")

    short_because = []
    for c in collection.constraints:
        if len(c.because) < 10:
            short_because.append(
                f"Constraint '{c.id or c.constraint_type.value}': because too short ({len(c.because)} chars)"
            )

    if short_because:
        for msg in short_because:
            results["warnings"].append(msg)
            if not json_output:
                console.print(f"  [yellow]⚠[/] {msg}")

        if strict:
            results["passed"] = False
    else:
        if not json_output:
            console.print("  [green]✓[/] All constraints have meaningful rationale")
        results["info"].append("All constraints have meaningful rationale (>=10 chars)")

    # Output results
    if json_output:
        print(json_module.dumps(results, indent=2))
    else:
        console.print("\n" + "─" * 50)
        if results["passed"] and (not strict or not results["warnings"]):
            console.print("[bold green]✓ Validation passed[/]")
        else:
            console.print("[bold red]✗ Validation failed[/]")
        console.print(
            f"  {len(results['errors'])} errors, "
            f"{len(results['warnings'])} warnings, "
            f"{len(results['info'])} info"
        )

    # Exit code
    if strict:
        sys.exit(0 if results["passed"] and not results["warnings"] else 1)
    else:
        sys.exit(0 if results["passed"] else 1)


@pcl.command("show")
@click.argument("pcl_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--tier",
    type=click.Choice(["hard", "strong", "soft", "all"]),
    default="all",
    help="Filter by constraint tier.",
)
@click.option(
    "--type",
    "constraint_type",
    type=str,
    default=None,
    help="Filter by constraint type (e.g., adjacent, separated).",
)
@click.option(
    "--json-output",
    is_flag=True,
    default=False,
    help="Output as JSON.",
)
def pcl_show(
    pcl_file: Path,
    tier: str,
    constraint_type: str | None,
    json_output: bool,
) -> None:
    """
    Display constraints from a PCL file.

    Shows a formatted table or JSON of all constraints with their
    parameters, tiers, and rationale.

    Examples:
        temper-placer pcl show constraints.yaml
        temper-placer pcl show constraints.yaml --tier hard
        temper-placer pcl show constraints.yaml --type adjacent --json-output
    """
    import json as json_module

    from temper_placer.pcl import ConstraintTier, ConstraintType, parse_pcl_file

    try:
        collection = parse_pcl_file(pcl_file)
    except Exception as e:
        console.print(f"[red]Failed to parse: {e}[/]")
        sys.exit(1)

    # Filter by tier
    constraints = collection.constraints
    if tier != "all":
        tier_enum = ConstraintTier[tier.upper()]
        constraints = [c for c in constraints if c.tier == tier_enum]

    # Filter by type
    if constraint_type:
        type_enum = ConstraintType(constraint_type.lower())
        constraints = [c for c in constraints if c.constraint_type == type_enum]

    if json_output:
        output = {
            "file": str(pcl_file),
            "total": len(collection),
            "filtered": len(constraints),
            "constraints": [
                {
                    "id": c.id or f"{c.constraint_type.value}_{i}",
                    "type": c.constraint_type.value,
                    "tier": c.tier.name,
                    "because": c.because,
                    **c.to_dict(),
                }
                for i, c in enumerate(constraints)
            ],
        }
        print(json_module.dumps(output, indent=2))
    else:
        console.print(f"[bold blue]PCL Constraints:[/] {pcl_file}")
        console.print(f"Showing {len(constraints)} of {len(collection)} constraints\n")

        table = Table(title="Constraints")
        table.add_column("ID", style="cyan", width=12)
        table.add_column("Type", style="green", width=10)
        table.add_column("Tier", style="yellow", width=8)
        table.add_column("Details", width=30)
        table.add_column("Because", style="dim", width=30)

        for i, c in enumerate(constraints):
            cid = c.id or f"{c.constraint_type.value[:3]}_{i}"
            ctype = c.constraint_type.value
            ctier = c.tier.name

            # Build details string based on type
            if hasattr(c, "a") and hasattr(c, "b"):
                details = f"{c.a} ↔ {c.b}"
                if hasattr(c, "max_distance_mm"):
                    details += f" ≤{c.max_distance_mm}mm"
                elif hasattr(c, "min_distance_mm"):
                    details += f" ≥{c.min_distance_mm}mm"
            elif hasattr(c, "components"):
                details = ", ".join(c.components[:3])
                if len(c.components) > 3:
                    details += f" +{len(c.components) - 3}"
            elif hasattr(c, "loop_name"):
                details = f"loop:{c.loop_name} ≤{c.max_area_mm2}mm²"  # type: ignore[attr-defined]
            elif hasattr(c, "component"):
                details = c.component
            else:
                details = str(c)[:30]

            # Truncate because
            because = c.because[:27] + "..." if len(c.because) > 30 else c.because

            table.add_row(cid, ctype, ctier, details, because)

        console.print(table)


@main.command()
@click.argument("component")
@click.option(
    "--trace", type=click.Path(exists=True, path_type=Path), help="Path to decision trace JSON"
)
@click.option("--history", is_flag=True, help="Show complete decision history")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information")
def why(
    component: str, trace: Path | None, history: bool, output_json: bool, _verbose: bool
) -> None:
    """Explain why a component is at its current position.

    Example:
        temper-placer why Q1
        temper-placer why Q1 --trace decisions.json --history
    """
    from temper_placer.explainability import load_trace

    # Find trace file
    if trace is None:
        trace = Path(".temper-placer/decisions.json")
        if not trace.exists():
            console.print(
                "[red]Error:[/] No decision trace found. Run optimization first or specify --trace."
            )
            sys.exit(1)

    # Load trace
    try:
        decision_trace = load_trace(trace)
    except Exception as e:
        console.print(f"[red]Error loading trace:[/] {e}")
        sys.exit(1)

    # Get explanation
    explanation = decision_trace.history(component) if history else decision_trace.why(component)

    if output_json:
        # Get decisions for component
        decisions = [d for d in decision_trace.decisions if d.subject == component]
        output = {
            "component": component,
            "decision_count": len(decisions),
            "decisions": [
                {
                    "type": d.decision_type.value,
                    "phase": d.phase.value if d.phase else None,
                    "value": d.value,
                    "reason": d.reason,
                    "epoch": d.epoch,
                }
                for d in decisions
            ],
        }
        print(json.dumps(output, indent=2))
    else:
        console.print(explanation)


@main.command()
@click.argument("component")
@click.argument("position")
@click.option(
    "--trace", type=click.Path(exists=True, path_type=Path), help="Path to decision trace JSON"
)
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information")
def why_not(
    component: str, position: str, trace: Path | None, output_json: bool, _verbose: bool
) -> None:
    """Explain why a particular position was rejected.

    Example:
        temper-placer why-not Q1 "(50, 10)"
        temper-placer why-not Q1 50,10
    """
    from temper_placer.explainability import load_trace

    # Parse position string
    try:
        # Handle formats: "(50, 10)", "50,10", "(50.0, 10.0)"
        cleaned = position.strip().replace("(", "").replace(")", "")
        parts = cleaned.split(",")
        pos_tuple = (float(parts[0].strip()), float(parts[1].strip()))
    except (ValueError, IndexError):
        console.print(f"[red]Error:[/] Invalid position format: {position}")
        console.print("Expected format: '(x, y)' or 'x,y'")
        sys.exit(1)

    # Find trace file
    if trace is None:
        trace = Path(".temper-placer/decisions.json")
        if not trace.exists():
            console.print(
                "[red]Error:[/] No decision trace found. Run optimization first or specify --trace."
            )
            sys.exit(1)

    # Load trace
    try:
        decision_trace = load_trace(trace)
    except Exception as e:
        console.print(f"[red]Error loading trace:[/] {e}")
        sys.exit(1)

    # Get explanation
    explanation = decision_trace.why_not(component, pos_tuple)

    if output_json:
        # Find the decision with rejected alternatives
        relevant_decision = None
        for d in decision_trace.decisions:
            if d.subject == component:
                for alt in d.alternatives:
                    if (
                        abs(alt.value[0] - pos_tuple[0]) < 0.1
                        and abs(alt.value[1] - pos_tuple[1]) < 0.1
                    ):
                        relevant_decision = d
                        break

        if relevant_decision:
            matching_alts = [
                {
                    "value": alt.value,
                    "rejection_reason": alt.rejection_reason,
                    "constraint_violated": alt.constraint_violated,
                    "loss_if_chosen": alt.loss_if_chosen,
                }
                for alt in relevant_decision.alternatives
                if abs(alt.value[0] - pos_tuple[0]) < 0.1 and abs(alt.value[1] - pos_tuple[1]) < 0.1
            ]
            output = {
                "component": component,
                "position": pos_tuple,
                "rejected": len(matching_alts) > 0,
                "alternatives": matching_alts,
            }
        else:
            output = {
                "component": component,
                "position": pos_tuple,
                "rejected": False,
                "alternatives": [],
            }

        print(json.dumps(output, indent=2))
    else:
        console.print(explanation)


@main.command()
@click.option(
    "--trace", type=click.Path(exists=True, path_type=Path), help="Path to decision trace JSON"
)
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def trace_info(trace: Path | None, output_json: bool) -> None:
    """Show summary of a decision trace.

    Example:
        temper-placer trace-info
        temper-placer trace-info --trace decisions.json
    """
    from temper_placer.explainability import load_trace

    # Find trace file
    if trace is None:
        trace = Path(".temper-placer/decisions.json")
        if not trace.exists():
            console.print(
                "[red]Error:[/] No decision trace found. Run optimization first or specify --trace."
            )
            sys.exit(1)

    # Load trace
    try:
        decision_trace = load_trace(trace)
    except Exception as e:
        console.print(f"[red]Error loading trace:[/] {e}")
        sys.exit(1)

    # Get summary
    summary = decision_trace.summary()

    if output_json:
        print(json.dumps(summary, indent=2))
    else:
        console.print("[bold]Decision Trace Summary[/]\n")
        console.print(f"Run ID: {summary.get('run_id', 'N/A')}")
        console.print(f"Total Decisions: {summary.get('total_decisions', 0)}")
        console.print(f"Components: {summary.get('component_count', 0)}")

        if summary.get("unique_subjects"):
            console.print(f"Subject List: {', '.join(sorted(summary['unique_subjects']))}")

        if "decisions_by_type" in summary:
            console.print("\n[bold]Decisions by Type:[/]")
            for dtype, count in summary["decisions_by_type"].items():
                console.print(f"  {dtype}: {count}")

        if "decisions_by_phase" in summary:
            console.print("\n[bold]Decisions by Phase:[/]")
            for phase, count in summary["decisions_by_phase"].items():
                console.print(f"  {phase}: {count}")

        if "final_metrics" in summary:
            console.print("\n[bold]Final Metrics:[/]")
            for key, value in summary["final_metrics"].items():
                console.print(f"  {key}: {value}")


@main.command()
@click.option(
    "--trace", type=click.Path(exists=True, path_type=Path), help="Path to decision trace JSON"
)
@click.option("--component", help="Filter by component")
@click.option("--phase", help="Filter by phase")
@click.option("--type", "dtype", help="Filter by decision type")
@click.option("--limit", type=int, help="Limit number of results")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def trace_list(
    trace: Path | None,
    component: str | None,
    phase: str | None,
    dtype: str | None,
    limit: int | None,
    output_json: bool,
) -> None:
    """List all decisions in a trace.

    Example:
        temper-placer trace-list --component Q1
        temper-placer trace-list --phase GEOMETRIC --limit 10
    """
    from temper_placer.explainability import load_trace

    # Find trace file
    if trace is None:
        trace = Path(".temper-placer/decisions.json")
        if not trace.exists():
            console.print(
                "[red]Error:[/] No decision trace found. Run optimization first or specify --trace."
            )
            sys.exit(1)

    # Load trace
    try:
        decision_trace = load_trace(trace)
    except Exception as e:
        console.print(f"[red]Error loading trace:[/] {e}")
        sys.exit(1)

    # Apply filters
    decisions = decision_trace.decisions
    if component:
        decisions = [d for d in decisions if d.subject == component]
    if phase:
        decisions = [d for d in decisions if d.phase and d.phase.value == phase]
    if dtype:
        decisions = [d for d in decisions if d.decision_type.value == dtype]
    if limit:
        decisions = decisions[:limit]

    if output_json:
        output = [
            {
                "subject": d.subject,
                "type": d.decision_type.value,
                "phase": d.phase.value if d.phase else None,
                "value": d.value,
                "reason": d.reason,
                "timestamp": d.timestamp.isoformat(),
            }
            for d in decisions
        ]
        print(json.dumps(output, indent=2))
    else:
        console.print(
            f"[bold]Decisions:[/] (showing {len(decisions)} of {len(decision_trace.decisions)} total)\n"
        )

        for d in decisions:
            phase_str = f"[{d.phase.value}]" if d.phase else ""
            console.print(f"• {d.subject} {phase_str} - {d.decision_type.value} ({d.id})")
            console.print(f"  Value: {d.value}")
            console.print(f"  Reason: {d.reason}")
            console.print()


@main.command()
@click.option(
    "--trace",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to decision trace JSON",
)
@click.option(
    "--format",
    type=click.Choice(["markdown", "html", "json"]),
    default="markdown",
    help="Output format",
)
@click.option(
    "-o", "--output", type=click.Path(path_type=Path), help="Output file (stdout if not specified)"
)
def trace_export(trace: Path, format: str, output: Path | None) -> None:
    """Export decision trace to various formats.

    Example:
        temper-placer trace-export --trace decisions.json --format html -o report.html
        temper-placer trace-export --trace decisions.json --format markdown
    """
    from temper_placer.explainability import (
        load_trace,
        render_markdown_report,
        save_html_report,
        save_markdown_report,
        trace_to_json,
    )

    # Load trace
    try:
        decision_trace = load_trace(trace)
    except Exception as e:
        console.print(f"[red]Error loading trace:[/] {e}")
        sys.exit(1)

    # Generate output based on format
    try:
        if format == "json":
            json_str = trace_to_json(decision_trace)
            if output:
                output.write_text(json_str)
                console.print(f"[green]✓[/] JSON exported to {output}")
            else:
                print(json_str)

        elif format == "markdown":
            if output:
                save_markdown_report(decision_trace, output)
                console.print(f"[green]✓[/] Markdown report exported to {output}")
            else:
                md_content = render_markdown_report(decision_trace)
                print(md_content)

        elif format == "html":
            if not output:
                console.print("[red]Error:[/] HTML format requires --output flag")
                sys.exit(1)
            save_html_report(decision_trace, output)
            console.print(f"[green]✓[/] HTML report exported to {output}")

    except Exception as e:
        console.print(f"[red]Error exporting trace:[/] {e}")
        sys.exit(1)


# =============================================================================
# Pipeline Commands
# =============================================================================


@main.command()  # type: ignore[no-redef]
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
    orchestrator = PipelineOrchestrator(config)  # type: ignore[arg-type]

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

        orchestrator.on_phase_start = on_phase_start  # type: ignore[assignment]
        orchestrator.on_phase_complete = on_phase_complete  # type: ignore[assignment]
        orchestrator.on_iteration = on_iteration  # type: ignore[assignment]
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




main.add_command(version)


@main.command()
@click.option(
    "--repo-root",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Repository root (default: auto-detect).",
)
@click.option(
    "--boards",
    type=str,
    default=None,
    multiple=True,
    help="Specific board IDs to test.",
)
@click.option(
    "--with-routing",
    is_flag=True,
    default=False,
    help="Include routing quality in GPBM comparison.",
)
def regression(
    repo_root: Path | None,
    boards: tuple[str, ...],
    with_routing: bool,
) -> None:
    """
    Run golden-board regression suite against frozen GPBM baselines.

    Tests all golden boards and reports pass/fail per board.
    Exits 0 if all boards pass, 1 if any board regresses.

    Example:
        temper-placer regression
        temper-placer regression --boards temper_placed
    """
    from temper_placer.regression.cli import run_regression

    class Args:
        pass

    args = Args()
    args.repo_root = str(repo_root) if repo_root else None  # type: ignore[attr-defined]
    args.boards = list(boards) if boards else None  # type: ignore[attr-defined]
    args.with_routing = with_routing  # type: ignore[attr-defined]

    sys.exit(run_regression(args))  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
