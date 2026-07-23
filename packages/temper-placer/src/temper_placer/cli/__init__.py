"""temper-placer CLI dispatcher — discovers subcommands via entry_points."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.panel import Panel
from rich.table import Table

from temper_placer._version import __version__
from temper_placer.profiling.cli import profile

from ._io import console
from .andon_commands import andon
from .timing import timing
from .trace_commands import trace
from .version import version
from .watch_commands import watch


@click.group()
@click.version_option(version=__version__, prog_name="temper-placer")
def main() -> None:
    """temper-placer: CP-SAT-based PCB placement optimizer."""
    pass


main.add_command(trace)
main.add_command(andon)
main.add_command(timing)
main.add_command(profile)
main.add_command(watch)


def _maybe_surface_unsat(result: object, unsat_report_path: Path | None) -> None:
    """Surface UNSAT report if the result carries one.

    Handles both CpSatPlacementResult.unsat_core (list of {name, because})
    and UnsatReport dataclass from the F4 acceptance gate workstream.
    """
    if result is None:
        return

    unsat = getattr(result, "unsat_report", None) or getattr(result, "unsat_core", None)
    if not unsat:
        return

    # Handle simplified unsat_core list from CpSatPlacementResult.
    if isinstance(unsat, list) and unsat:
        console.print(
            Panel(
                "\n".join(
                    f"  • {e.get('name', '?')}"
                    + (f"\n    because: {e['because']}" if e.get('because') else "")
                    for e in unsat
                ),
                border_style="red",
                title="UNSAT Core",
            ),
            style="",
        )
        if unsat_report_path is not None:
            import json as _json
            unsat_report_path.write_text(_json.dumps(unsat, indent=2), encoding="utf-8")
            console.print(f"[yellow]UNSAT report written to:[/] {unsat_report_path}")
        return

    try:
        from temper_placer.placer.cp_sat.unsat_surface import (
            format_unsat_panel,
            write_unsat_json,
        )

        console.print(
            Panel(format_unsat_panel(unsat), border_style="red", title="UNSAT Core"),
            style="",
        )

        if unsat_report_path is not None:
            write_unsat_json(unsat, unsat_report_path)
            console.print(f"[yellow]UNSAT report written to:[/] {unsat_report_path}")
    except ImportError:
        console.print("[red]Failed to import UNSAT surface module.[/]")


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
    type=click.Choice(["cp-sat", "jax-deprecated"]),
    default="cp-sat",
    show_default=True,
    help="Placer engine to use.",
)
@click.option(
    "--loop/--no-loop",
    default=True,
    help="Enable place→route feedback loop for routing-aware placement (default: enabled).",
)
@click.option(
    "--unsat-report",
    type=click.Path(path_type=Path),
    default=None,
    help="Write UNSAT core report as JSON to this path when CP-SAT returns INFEASIBLE.",
)
@click.option(
    "--all-gates",
    is_flag=True,
    default=False,
    help="Register all five gates (DRC, Routing, Stackup, Physics, Quality) on the place-route loop.",
)
@click.option(
    "--warm-start",
    is_flag=True,
    default=False,
    help="Seed CP-SAT solver with deterministic pipeline positions via AddHint.",
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
    placer: str,
    loop: bool,
    unsat_report: Path | None,
    all_gates: bool,
    warm_start: bool,
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
            f"[bold blue]temper-placer[/] v{__version__}\nCP-SAT PCB placement optimizer",
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

    if placer == "jax-deprecated":
        sys.stderr.write(
            "The JAX placer has been removed; CP-SAT is the sole placer.\n"
            "If you reached this flag for production-rollback reasons, "
            "file an issue with the board's PCL config and the routed-PCB file.\n"
        )
        console.print("[dim]Exiting with code 0 (informational, not an error).[/]")
        sys.exit(0)

    # CP-SAT placer (default, sole active path)
    console.print()
    console.print("[bold green]CP-SAT placer selected (default).[/]")
    console.print("[dim]The JAX gradient-descent pipeline has been removed.[/]")

    # Place→Route feedback loop (U4)
    if loop:
        console.print("\n[bold cyan]Running place→route feedback loop...[/]")
        try:
            from temper_placer.io.config_loader import load_constraints
            from temper_placer.io.kicad_parser import parse_kicad_pcb
            from temper_placer.placer.cp_sat.loop import PlaceRouteLoop

            parse_result = parse_kicad_pcb(input_pcb)
            netlist = parse_result.netlist
            board = parse_result.board
            assert board is not None, "Board geometry parsing failed"
            constraints = load_constraints(config)

            loop_runner = PlaceRouteLoop()
            pcl_constraints = list(getattr(constraints, "pcl_constraints", []))
            # Also load inline constraints from the config YAML if present.
            if not pcl_constraints:
                try:
                    import yaml as _yaml

                    from temper_placer.pcl.parser import parse_constraint_dict
                    raw = config.read_text(encoding="utf-8") if hasattr(config, "read_text") else ""
                    if raw:
                        cfg = _yaml.safe_load(raw)
                        inline = cfg.get("constraints", []) if isinstance(cfg, dict) else []
                        for cdict in inline:
                            from contextlib import suppress
                            with suppress(Exception):
                                pcl_constraints.append(parse_constraint_dict(cdict))
                except Exception:
                    pass

            # Load zone definitions from the cooker constraint config.
            cooker_path = Path("packages/temper-placer/configs/constraints/temper_induction_cooker.yaml")
            zone_objs = []
            zone_comps: dict[str, list[str]] = {}
            if cooker_path.exists():
                import yaml as _yaml2
                cooker = _yaml2.safe_load(cooker_path.read_text())
                for zd in cooker.get("zones", []):
                    z = type("Zone", (), {
                        "name": zd["name"],
                        "bounds": tuple(zd["bounds"]),
                        "components": zd.get("components", []),
                    })()
                    zone_objs.append(z)
                if zone_objs:
                    board.zones = zone_objs

            # Derive zone component lists from enclosing constraints.
            for c in pcl_constraints:
                outer = getattr(c, "outer", None)
                inner = getattr(c, "inner", None)
                if outer and inner:
                    zone_comps[outer] = list(set(
                        zone_comps.get(outer, []) + list(inner)
                    ))

            # Load loop component definitions from pcb_spec.yaml.
            loop_comps: dict[str, list[str]] = {}
            spec_path = Path("packages/temper-placer/configs/pcb_spec.yaml")
            if spec_path.exists():
                import yaml as _yaml3
                spec = _yaml3.safe_load(spec_path.read_text())
                emi = spec.get("emi", {})
                for name, comps in emi.get("loop_components", {}).items():
                    loop_comps[name] = comps
            loop_result = loop_runner.run(
                netlist=netlist,
                board=board,
                pcl_constraints=pcl_constraints,
                seed=seed,
                zones={z.name: z.bounds for z in zone_objs} if zone_objs else None,
                zone_components=zone_comps if zone_comps else None,
                loop_components=loop_comps if loop_comps else None,
                all_gates=all_gates,
                source_pcb_path=input_pcb,
            )

            # Surface UNSAT core from CP-SAT placement result.
            _maybe_surface_unsat(loop_result.placement, unsat_report)

            if loop_result.success:
                console.print(
                    f"  [green]âœ“[/] Loop converged in {len(loop_result.rounds)} rounds"
                )
                console.print(
                    f"    Routing completion: {getattr(loop_result.routing, 'completion_rate', 0.0)*100:.1f}%"
                )

                # Gate results summary when all_gates was used.
                gate_results = getattr(loop_runner, '_gate_results', {})
                if gate_results:
                    from ..placer.cp_sat.gates import GateStatus
                    table = Table(title="Gate Results", show_header=True)
                    table.add_column("Gate", style="cyan")
                    table.add_column("Status")
                    table.add_column("Violations")
                    for gname, gr in sorted(gate_results.items()):
                        status_str = (
                            "[green]CLEAN[/]" if gr.status is GateStatus.CLEAN
                            else "[yellow]UNMEASURED[/]"
                            if gr.status is GateStatus.UNMEASURED
                            else "[red]VIOLATIONS[/]"
                        )
                        vcount = str(len(gr.violations))
                        table.add_row(gname, status_str, vcount)
                    console.print(table)

                # Surface UNMEASURED data.
                unmeasured = getattr(loop_result, 'unmeasured_gates', {})
                if unmeasured:
                    console.print(
                        "[yellow]UNMEASURED gates:[/] "
                        + ", ".join(unmeasured.keys())
                    )
                    for gname, msg in unmeasured.items():
                        console.print(
                            f"  [dim]{gname}: {msg[:120]}[/]"
                        )

                # The loop routes the authoritative source board directly;
                # retain that exact artifact rather than issuing a second,
                # potentially divergent route pass here.
                if loop_result.placement is not None:
                    routed_body = getattr(loop_result.routing, "routed_pcb_content", None)
                    if not routed_body:
                        raise click.ClickException(
                            "Place→route loop converged without an authoritative routed PCB artifact"
                        )
                    output.write_text(routed_body, encoding="utf-8")
                    console.print(f"    Output: {output}")

                    # Run KiCad DRC on the placed output.
                    console.print("\n[bold]Running KiCad DRC (truth gate)...[/]")
                    try:
                        import json
                        import os
                        import subprocess
                        import tempfile

                        drc_out = Path(tempfile.mktemp(suffix=".json"))
                        result = subprocess.run(
                            ["kicad-cli", "pcb", "drc", "--format", "json",
                             "-o", str(drc_out), str(output)],
                            capture_output=True, text=True, timeout=120,
                        )
                        if drc_out.exists():
                            with open(drc_out) as f:
                                drc_data = json.load(f)
                            violations = drc_data.get("violations", [])
                            errors = [v for v in violations if v.get("severity") == "error"]
                            warnings = [v for v in violations if v.get("severity") == "warning"]
                            if errors:
                                console.print(f"  [red]DRC: {len(errors)} errors, {len(warnings)} warnings[/]")
                                for e in errors[:5]:
                                    console.print(f"    ERROR: {e.get('type','?')} — {e.get('description','')[:100]}")
                                raise click.ClickException(
                                    f"KiCad DRC found {len(errors)} error(s) in {output}"
                                )
                            else:
                                console.print(f"  [green]DRC: 0 errors, {len(warnings)} warnings[/]")
                            os.unlink(drc_out)
                        else:
                            raise click.ClickException(
                                f"KiCad DRC report was not produced: {result.stderr[:200]}"
                            )
                    except click.ClickException:
                        raise
                    except Exception as drc_e:
                        raise click.ClickException(f"KiCad DRC could not run: {drc_e}") from drc_e
            else:
                console.print(
                    f"  [yellow]Loop did not converge: {loop_result.reason}[/]"
                )
                if loop_result.rounds:
                    last = loop_result.rounds[-1]
                    console.print(
                        f"    Best routing completion: {last.completion_rate*100:.1f}%"
                        f" ({last.drc_errors} DRC errors)"
                    )
                raise click.ClickException(
                    f"Place→route loop did not converge: {loop_result.reason}"
                )
        except click.ClickException:
            raise
        except Exception as e:
            raise click.ClickException(f"Place→route loop failed: {e}") from e
    else:
        # --no-loop: direct CP-SAT solve, no routing feedback
        console.print("\n[bold cyan]Running CP-SAT solver (--no-loop)...[/]")
        try:
            from temper_placer.io.config_loader import load_constraints
            from temper_placer.io.kicad_parser import parse_kicad_pcb
            from temper_placer.placer.cp_sat.encoder import solve_placement

            parse_result = parse_kicad_pcb(input_pcb)
            netlist = parse_result.netlist
            board = parse_result.board
            constraints = load_constraints(config)
            pcl_constraints = list(getattr(constraints, "pcl_constraints", []))

            console.print(f"  Parsed {len(netlist.components)} components from input PCB")
            console.print(f"  Loaded {len(pcl_constraints)} PCL constraints")

            # Warm-start: seed solver with deterministic pipeline positions.
            hint_positions = None
            if warm_start:
                console.print("  [cyan]Warm-start: running deterministic pipeline...[/]")
                from temper_placer.deterministic import BoardState, create_drc_aware_pipeline
                from temper_placer.io.kicad_metadata import extract_kicad_metadata

                metadata = extract_kicad_metadata(input_pcb)
                dp = create_drc_aware_pipeline(config=constraints, metadata=metadata)
                dp_state = BoardState(board=board, netlist=netlist)
                dp_state = dp.run(dp_state)
                if dp_state.placements:
                    hint_positions = {}
                    for ref, pos in dp_state.placements:
                        hint_positions[ref] = (pos[0], pos[1], 0)
                    console.print(
                        f"  [green]✓[/] Extracted {len(hint_positions)} hint positions"
                    )

            cp_result = solve_placement(
                netlist=netlist,
                board=board,
                extra_constraints=pcl_constraints,
                seed=seed,
                hint_positions=hint_positions,
            )

            console.print(
                f"  Solver status: {cp_result.status}"
                f" ({cp_result.solve_time_ms:.0f}ms)"
            )

            if cp_result.status in ("infeasible", "model_invalid"):
                _maybe_surface_unsat(cp_result, unsat_report)
                sys.exit(1)

            if cp_result.status in ("optimal", "feasible"):
                from temper_placer.io.kicad_writer import (
                    PlacementUpdate,
                    write_placements_to_pcb,
                )

                placements: dict[str, PlacementUpdate] = {}
                for ref, pos in cp_result.positions.items():
                    placements[ref] = PlacementUpdate(
                        ref=ref,
                        x=pos[0],
                        y=pos[1],
                        rotation=cp_result.rotations.get(ref, 0) * 90.0,
                    )

                write_result = write_placements_to_pcb(
                    template_pcb=input_pcb,
                    output_pcb=output,
                    placements=placements,
                    preserve_unmatched=True,
                    components=netlist.components,
                )
                console.print(
                    f"  [green]✓[/] {write_result.components_updated} components placed"
                )
                if write_result.has_warnings:
                    for w in write_result.warnings:
                        console.print(f"  [yellow]⚠[/] {w}")
                console.print(f"  Output: {output}")
            else:
                console.print(
                    f"  [red]Solver returned unexpected status: {cp_result.status}[/]"
                )
                sys.exit(1)
        except click.ClickException:
            raise
        except Exception as e:
            raise click.ClickException(f"CP-SAT solve failed: {e}") from e

    sys.exit(0)




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
