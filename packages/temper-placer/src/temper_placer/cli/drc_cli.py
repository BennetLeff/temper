"""
Command-line interface for DRC checking.

Moved from ``temper_drc.cli``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import click
import yaml  # type: ignore[import-untyped]

from temper_placer.validation.drc_result import (
    ClearanceCheck,
    ComponentOverlapCheck,
    CourtyardCheck,
    CreepageCheck,
    FloatingPinsCheck,
    GroundPlaneCheck,
    HVLVSeparationCheck,
    IsolationCheck,
    LoopAreaCheck,
    NetConnectivityCheck,
    NoiseCouplingCheck,
    PowerDomainCheck,
    ZoneContainmentCheck,
)
from temper_placer.validation.drc_runner import CheckRunner
from temper_placer.validation.drc_types import ConstraintSet, Placement
from temper_placer.report.formatter import format_html, format_json, format_text
from temper_placer.report.summary import generate_summary


@click.group()
@click.version_option(version="0.1.0")
def cli() -> None:
    """temper-drc: Standalone DRC/ERC checker for PCB designs."""
    pass


@cli.command()
@click.argument("placement_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-c",
    "--constraints",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="PCL constraints YAML file",
)
@click.option(
    "--category",
    multiple=True,
    type=click.Choice(["drc", "erc", "safety", "emc"]),
    help="Run specific category (can specify multiple)",
)
@click.option(
    "--format",
    type=click.Choice(["text", "json", "html"]),
    default="text",
    help="Output format",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="Output file (stdout if not specified)",
)
@click.option(
    "--fail-on-error/--no-fail-on-error",
    default=True,
    help="Exit with non-zero code on check failures",
)
@click.option(
    "--verbose/--no-verbose",
    default=False,
    help="Show detailed progress",
)
def check(
    placement_file: Path,
    constraints: Path,
    category: tuple[str, ...],
    format: str,
    output: Path | None,
    fail_on_error: bool,
    verbose: bool,
) -> None:
    """Run DRC/ERC checks on a placement file."""
    if verbose:
        click.echo(f"Loading placement from {placement_file}...", err=True)
    placement = Placement.from_yaml(placement_file)

    if verbose:
        click.echo(f"Loading constraints from {constraints}...", err=True)
    constraint_set = ConstraintSet.from_yaml(constraints)

    runner = CheckRunner()

    all_checks = [
        ClearanceCheck(),
        ComponentOverlapCheck(),
        CourtyardCheck(),
        ZoneContainmentCheck(),
        NetConnectivityCheck(),
        PowerDomainCheck(),
        FloatingPinsCheck(),
        HVLVSeparationCheck(),
        CreepageCheck(),
        IsolationCheck(),
        LoopAreaCheck(),
        NoiseCouplingCheck(),
        GroundPlaneCheck(),
    ]
    runner.add_checks(all_checks)

    if verbose:
        def on_start(check: Any) -> None:
            click.echo(f"  Running {check.name}...", err=True)

        def on_complete(check: Any, result: Any) -> None:
            status = "✓" if result.passed else "✗"
            click.echo(f"  {status} {check.name} ({result.elapsed_ms:.1f}ms)", err=True)

        runner.on_check_start = on_start  # type: ignore[attr-defined]
        runner.on_check_complete = on_complete  # type: ignore[attr-defined]

    categories_list = list(category) if category else None
    if verbose:
        if categories_list:
            click.echo(f"Running categories: {', '.join(categories_list)}", err=True)
        else:
            click.echo("Running all checks...", err=True)

    result = runner.run(placement, constraint_set, categories=categories_list)

    if format == "text":
        output_str = format_text(result)
    elif format == "json":
        output_str = format_json(result)
    elif format == "html":
        output_str = format_html(result, placement_file.name, constraint_set)
    else:
        raise ValueError(f"Unknown format: {format}")

    if output:
        output.write_text(output_str)
        if verbose:
            click.echo(f"Report written to {output}", err=True)
    else:
        click.echo(output_str)

    if fail_on_error and not result.passed:
        sys.exit(1)


@cli.command()
@click.argument("placement_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-c",
    "--constraints",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="PCL constraints YAML file",
)
@click.option(
    "--category",
    multiple=True,
    type=click.Choice(["drc", "erc", "safety", "emc"]),
    help="Summarize specific category (can specify multiple)",
)
def summary(
    placement_file: Path,
    constraints: Path,
    category: tuple[str, ...],
) -> None:
    """Generate metrics summary for a placement."""
    placement = Placement.from_yaml(placement_file)
    constraint_set = ConstraintSet.from_yaml(constraints)

    runner = CheckRunner()
    all_checks = [
        ClearanceCheck(),
        ComponentOverlapCheck(),
        CourtyardCheck(),
        ZoneContainmentCheck(),
        NetConnectivityCheck(),
        PowerDomainCheck(),
        FloatingPinsCheck(),
        HVLVSeparationCheck(),
        CreepageCheck(),
        IsolationCheck(),
        LoopAreaCheck(),
        NoiseCouplingCheck(),
        GroundPlaneCheck(),
    ]
    runner.add_checks(all_checks)

    categories_list = list(category) if category else None
    result = runner.run(placement, constraint_set, categories=categories_list)

    summary_text = generate_summary(result, placement, constraint_set)
    click.echo(summary_text)


@cli.command()
def list_checks() -> None:
    """List all available checks."""
    checks_by_category = {
        "DRC": [
            "drc_clearance - Component-to-component clearance",
            "drc_component_overlap - Component overlap detection",
            "drc_courtyard - Courtyard clearance violations",
            "drc_zone_containment - Zone membership verification",
        ],
        "ERC": [
            "erc_net_connectivity - Net connectivity verification",
            "erc_power_domain - Power domain isolation",
            "erc_floating_pins - Unconnected pin detection",
        ],
        "Safety": [
            "safety_hv_lv_separation - HV/LV separation (IEC 60335)",
            "safety_creepage - Creepage distance verification",
            "safety_isolation - Isolation barrier integrity",
        ],
        "EMC": [
            "emc_loop_area - Critical loop area analysis",
            "emc_noise_coupling - Noise-sensitive component isolation",
            "emc_ground_plane - Ground plane continuity",
        ],
    }

    click.echo("Available Checks:\n")
    for category, checks in checks_by_category.items():
        click.echo(f"{category}:")
        for check in checks:
            click.echo(f"  - {check}")
        click.echo()


@cli.command()
@click.argument("output_file", type=click.Path(path_type=Path))
@click.option("--board-width", type=float, default=100.0, help="Board width in mm")
@click.option("--board-height", type=float, default=100.0, help="Board height in mm")
def init_placement(
    output_file: Path,
    board_width: float,
    board_height: float,
) -> None:
    """Create a template placement YAML file."""
    template = {
        "board_width": board_width,
        "board_height": board_height,
        "components": [
            {
                "ref": "U1",
                "footprint": "SOIC-8",
                "x": 50.0,
                "y": 50.0,
                "rotation": 0.0,
                "layer": "F.Cu",
                "width": 5.0,
                "height": 4.0,
                "net_class": "Signal",
                "voltage_domain": "3V3",
            }
        ],
        "nets": {"VCC": ["U1"], "GND": ["U1"]},
        "zones": [
            {"name": "Power", "bounds": [0, 0, 40, 100]},
            {"name": "Digital", "bounds": [40, 0, 100, 100]},
        ],
        "net_classes": {"VCC": "Power", "GND": "Power"},
        "voltage_domains": {"VCC": "3V3", "GND": "GND"},
    }

    with open(output_file, "w") as f:
        yaml.dump(template, f, default_flow_style=False, sort_keys=False)
    click.echo(f"Template placement created: {output_file}")


@cli.command()
@click.argument("output_file", type=click.Path(path_type=Path))
@click.option("--hv-clearance", type=float, default=10.0, help="HV/LV clearance in mm")
def init_constraints(
    output_file: Path,
    hv_clearance: float,
) -> None:
    """Create a template constraints YAML file."""
    template = {
        "clearances": {
            "Signal-Signal": 0.2,
            "Signal-Power": 0.3,
            "Power-Power": 0.5,
            "HV-HV": 2.0,
            "HV-Signal": 10.0,
        },
        "hv_clearance_mm": hv_clearance,
        "creepage_mm": 6.0,
        "isolation_mm": 6.0,
        "courtyard_clearance_mm": 0.25,
        "max_loop_area_mm2": 100.0,
        "noise_sensitive_clearance_mm": 5.0,
    }

    with open(output_file, "w") as f:
        yaml.dump(template, f, default_flow_style=False, sort_keys=False)
    click.echo(f"Template constraints created: {output_file}")


def main() -> None:
    """Entry point for CLI."""
    cli()


if __name__ == "__main__":
    main()
