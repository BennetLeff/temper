"""
KiCad PCB route exporter (temper-wnyn).

Exports router RoutePath objects to KiCad PCB files with trace segments and vias.
"""

from dataclasses import dataclass
from pathlib import Path

from kiutils.board import Board as KiBoard
from kiutils.items.brditems import Segment, Via
from kiutils.items.common import Position

from temper_placer.routing.grid_converter import grid_to_world
from temper_placer.routing.maze_router import RoutePath
from temper_placer.routing.path_simplify import simplify_path


# Layer mapping from grid layer index to KiCad layer name
DEFAULT_LAYER_MAP = {
    0: "F.Cu",  # Top copper
    1: "B.Cu",  # Bottom copper
    2: "In1.Cu",  # Inner layer 1 (for 4-layer boards)
    3: "In2.Cu",  # Inner layer 2 (for 4-layer boards)
}


@dataclass
class TraceSegment:
    """A single trace segment for export."""

    net: str
    start: tuple[float, float]
    end: tuple[float, float]
    width: float
    layer: str  # "F.Cu" or "B.Cu"


@dataclass
class TraceVia:
    """A via connecting layers."""

    net: str
    position: tuple[float, float]
    size: float  # Outer diameter
    drill: float  # Drill diameter
    layers: list[str]  # e.g., ["F.Cu", "B.Cu"]


@dataclass
class ExportResult:
    """Result of exporting routes to PCB file."""

    output_path: Path
    segments_added: int
    vias_added: int
    nets_exported: int
    nets_failed: int
    warnings: list[str]

    def __str__(self) -> str:
        return (
            f"Export complete: {self.nets_exported} nets, "
            f"{self.segments_added} segments, {self.vias_added} vias → {self.output_path}"
        )


def path_to_segments(
    path: RoutePath,
    origin: tuple[float, float],
    cell_size: float,
    trace_width: float,
    layer_map: dict[int, str] | None = None,
) -> list[TraceSegment]:
    """Convert path to trace segments.

    Applies path simplification before conversion to reduce segment count.
    Skips cells where layer transitions occur (via locations).

    Args:
        path: RoutePath from maze router
        origin: PCB origin (x0, y0) in mm
        cell_size: Grid cell size in mm
        trace_width: Trace width in mm
        layer_map: Optional layer index to name mapping

    Returns:
        List of TraceSegment objects

    Example:
        >>> path = RoutePath(
        ...     net="GND",
        ...     cells=[GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(2, 0, 0)],
        ...     length=2.0,
        ...     via_count=0,
        ...     success=True,
        ... )
        >>> segments = path_to_segments(path,  origin=(0, 0), cell_size=1.0, trace_width=0.25)
        >>> len(segments)
        1  # Simplified to start→end
    """
    if not path.success or len(path.cells) < 2:
        return []

    layer_map = layer_map or DEFAULT_LAYER_MAP
    simplified_cells = simplify_path(path.cells)
    segments = []

    for i in range(1, len(simplified_cells)):
        c1, c2 = simplified_cells[i - 1], simplified_cells[i]

        # Layer transition creates a via, not a segment
        if c1.layer != c2.layer:
            continue

        # Convert grid to world coordinates
        start = grid_to_world(c1, origin, cell_size)
        end = grid_to_world(c2, origin, cell_size)
        layer_name = layer_map.get(c1.layer, "F.Cu")

        segments.append(
            TraceSegment(
                net=path.net,
                start=start,
                end=end,
                width=trace_width,
                layer=layer_name,
            )
        )

    return segments


def path_to_vias(
    path: RoutePath,
    origin: tuple[float, float],
    cell_size: float,
    via_size: float = 0.8,
    via_drill: float = 0.4,
    layer_map: dict[int, str] | None = None,
) -> list[TraceVia]:
    """Extract vias from layer transitions in path.

    Args:
        path: RoutePath from maze router
        origin: PCB origin (x0, y0) in mm
        cell_size: Grid cell size in mm
        via_size: Via outer diameter in mm
        via_drill: Via drill diameter in mm
        layer_map: Optional layer index to name mapping

    Returns:
        List of TraceVia objects

    Example:
        >>> path = RoutePath(
        ...     net="SPI_CLK",
        ...     cells=[GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(1, 0, 1)],
        ...     length=1.0,
        ...     via_count=1,
        ...     success=True,
        ... )
        >>> vias = path_to_vias(path, origin=(0, 0), cell_size=1.0)
        >>> len(vias)
        1
    """
    if not path.success or len(path.cells) < 2:
        return []

    layer_map = layer_map or DEFAULT_LAYER_MAP
    vias = []

    for i in range(1, len(path.cells)):
        c1, c2 = path.cells[i - 1], path.cells[i]

        # Detect layer transition
        if c1.layer != c2.layer:
            # Via is placed at the location where layer changes
            # Use the position of the cell AFTER the transition
            pos = grid_to_world(c2, origin, cell_size)

            # For through-hole via, specify all layers
            # For blind/buried via, would need specific layer pair
            all_layers = sorted([layer_map.get(c1.layer, "F.Cu"), layer_map.get(c2.layer, "B.Cu")])

            vias.append(
                TraceVia(
                    net=path.net,
                    position=pos,
                    size=via_size,
                    drill=via_drill,
                    layers=all_layers,
                )
            )

    return vias


def add_segments_to_board(
    board: KiBoard,
    segments: list[TraceSegment],
) -> int:
    """Add trace segments to KiCad board object.

    Uses kiutils.items.brditems.Segment to create PCB trace elements.

    Args:
        board: KiCad board object to modify
        segments: List of trace segments to add

    Returns:
        Number of segments added
    """
    added_count = 0

    for seg in segments:
        # Find net code (KiCad uses numeric net IDs)
        net_code = 0  # Default to unconnected
        for net in board.nets:
            if net.name == seg.net:
                net_code = net.number
                break

        # Create segment using kiutils
        kicad_seg = Segment(
            start=Position(X=seg.start[0], Y=seg.start[1]),
            end=Position(X=seg.end[0], Y=seg.end[1]),
            width=seg.width,
            layer=seg.layer,
            net=net_code,
            tstamp=None,  # KiCad will generate timestamp
        )

        board.traceItems.append(kicad_seg)
        added_count += 1

    return added_count


def add_vias_to_board(
    board: KiBoard,
    vias: list[TraceVia],
) -> int:
    """Add vias to KiCad board object.

    Uses kiutils.items.brditems.Via to create PCB via elements.

    Args:
        board: KiCad board object to modify
        vias: List of vias to add

    Returns:
        Number of vias added
    """
    added_count = 0

    for via in vias:
        # Find net code
        net_code = 0
        for net in board.nets:
            if net.name == via.net:
                net_code = net.number
                break

        # Create via using kiutils
        kicad_via = Via(
            at=Position(X=via.position[0], Y=via.position[1]),
            size=via.size,
            drill=via.drill,
            layers=via.layers,
            net=net_code,
            tstamp=None,
        )

        board.traceItems.append(kicad_via)
        added_count += 1

    return added_count


def export_routed_pcb(
    template_pcb: Path,
    routes: dict[str, RoutePath],
    output_pcb: Path,
    trace_widths: dict[str, float] | None = None,
    default_trace_width: float = 0.25,
    via_size: float = 0.8,
    via_drill: float = 0.4,
    origin: tuple[float, float] = (0.0, 0.0),
    cell_size: float = 1.0,
    layer_map: dict[int, str] | None = None,
) -> ExportResult:
    """Export routed paths to KiCad PCB file.

    Main export function that:
    1. Parses template PCB (has components, no traces)
    2. Converts successful routes to segments and vias
    3. Adds geometry to PCB using kiutils
    4. Writes output file

    Args:
        template_pcb: Path to input .kicad_pcb file with placed components
        routes: Dictionary of net_name → RoutePath from router
        output_pcb: Path to write output .kicad_pcb file
        trace_widths: Optional dict of net_name → trace width (mm)
        default_trace_width: Default trace width in mm
        via_size: Via outer diameter in mm
        via_drill: Via drill diameter in mm
        origin: PCB origin offset (x0, y0)
        cell_size: Router grid cell size in mm
        layer_map: Optional layer index → name mapping

    Returns:
        ExportResult with statistics and warnings

    Example:
        >>> routes = {
        ...     "GND": RoutePath(..., success=True),
        ...     "VCC": RoutePath(..., success=True),
        ...     "SIG1": RoutePath(..., success=False),
        ... }
        >>> result = export_routed_pcb(
        ...     "input.kicad_pcb",
        ...     routes,
        ...     "output.kicad_pcb",
        ... )
        >>> print(result)
        Export complete: 2 nets, 45 segments, 3 vias → output.kicad_pcb
    """
    # Load template PCB
    board = KiBoard.from_file(str(template_pcb))

    # Collect all segments and vias
    all_segments: list[TraceSegment] = []
    all_vias: list[TraceVia] = []
    nets_exported = 0
    nets_failed = 0
    warnings: list[str] = []

    for net_name, path in routes.items():
        if not path.success:
            nets_failed += 1
            warnings.append(f"Net {net_name} routing failed: {path.failure_reason}")
            continue

        # Determine trace width for this net
        trace_width = trace_widths.get(net_name, default_trace_width) if trace_widths else default_trace_width

        # Convert path to geometry
        segments = path_to_segments(path, origin, cell_size, trace_width, layer_map)
        vias = path_to_vias(path, origin, cell_size, via_size, via_drill, layer_map)

        all_segments.extend(segments)
        all_vias.extend(vias)
        nets_exported += 1

    # Add geometry to board
    segments_added = add_segments_to_board(board, all_segments)
    vias_added = add_vias_to_board(board, all_vias)

    # Write output file
    output_pcb = Path(output_pcb)
    output_pcb.parent.mkdir(parents=True, exist_ok=True)
    board.to_file(str(output_pcb))

    return ExportResult(
        output_path=output_pcb,
        segments_added=segments_added,
        vias_added=vias_added,
        nets_exported=nets_exported,
        nets_failed=nets_failed,
        warnings=warnings,
    )
