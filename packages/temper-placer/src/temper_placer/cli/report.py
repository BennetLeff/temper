"""report command for temper-placer CLI."""

from __future__ import annotations

import click
import json
import sys
from pathlib import Path
from ._io import console

@click.command()
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
