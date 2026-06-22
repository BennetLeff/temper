"""validate command for temper-placer CLI."""

from __future__ import annotations

import click
import json
import sys
from pathlib import Path
from ._io import console

@click.command()
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
