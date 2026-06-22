"""visualize command for temper-placer CLI."""

from __future__ import annotations

import click
import sys
from pathlib import Path
from ._io import console

@click.command()
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
                load_constraints,
                create_board_from_constraints,
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

        console.print("[green]✓[/] Opening in browser...")
        webbrowser.open(f"file://{temp_path}")

    console.print("[bold green]Done![/]")
