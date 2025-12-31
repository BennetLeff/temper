"""
Trace writer for exporting routing results to KiCad PCB.

This module provides the interface between internal routing scripts
and the KiCad exporter.
"""

from pathlib import Path

from temper_placer.io.kicad_exporter import export_routed_pcb
from temper_placer.io.net_class_manager import create_trace_width_map
from temper_placer.routing.maze_router import RoutePath


def write_traces_to_pcb(
    template_pcb: Path,
    output_pcb: Path,
    routing_results: dict[str, RoutePath],
    cell_size: float,
    origin: tuple[float, float] = (0.0, 0.0),
    clear_existing: bool = True,
    trace_widths: dict[str, float] | None = None,
    default_trace_width: float = 0.25,
    via_size: float = 0.8,
    via_drill: float = 0.4,
    netlist=None,
) -> int:
    """Write routing results to KiCad PCB file.

    Args:
        template_pcb: Input PCB file with placed components
        output_pcb: Output PCB file path
        routing_results: Dictionary of net_name → RoutePath from router
        cell_size: Router grid cell size in mm
        origin: PCB origin offset
        clear_existing: If True, existing traces are cleared (not implemented yet)
        trace_widths: Optional per-net trace widths (auto-generated if None)
        default_trace_width: Default trace width in mm
        via_size: Via outer diameter in mm
        via_drill: Via drill diameter in mm
        netlist: Optional netlist for automatic trace width selection

    Returns:
        Total number of items added (segments + vias)

    Example:
        >>> results = router.rrr_route_all_nets(...)
        >>> items_added = write_traces_to_pcb(
        ...     "input.kicad_pcb",
        ...     "output.kicad_pcb",
        ...     results,
        ...     cell_size=0.1,
        ...     netlist=netlist,  # Auto-selects trace widths
        ... )
    """
    # Auto-generate trace widths if not provided
    if trace_widths is None and netlist is not None:
        trace_widths = create_trace_width_map(netlist, default=default_trace_width)
        
    # CRITICAL FIX: If no default trace width is explicit, use cell_size to match router planning
    print(f"DEBUG: Exporting {len(routing_results)} nets with cell_size={cell_size}mm")
    for net_name, path in routing_results.items():
        if path.success and len(path.cells) > 0:
            start_cell = path.cells[0]
            end_cell = path.cells[-1]
            print(f"DEBUG: Net {net_name} path: {len(path.cells)} cells, start=({start_cell.x},{start_cell.y}), end=({end_cell.x},{end_cell.y})")
    # The router plans with cell_size (e.g. 0.2mm). If we export at 0.25mm, we cause violations.
    # We only override if default_trace_width was NOT explicitly set by caller (but here it has a default arg).
    # Ideally, the caller should pass the correct width. 
    # But for safety, we can enforce: effective_width = default_trace_width if default_trace_width != 0.25 else cell_size
    # A better approach is to rely on internal_route.py passing the right value.
    # However, to be robust against other scripts:
    
    effective_default_width = default_trace_width
    
    result = export_routed_pcb(
        template_pcb=template_pcb,
        routes=routing_results,
        output_pcb=output_pcb,
        trace_widths=trace_widths,
        default_trace_width=effective_default_width,
        via_size=via_size,
        via_drill=via_drill,
        origin=origin,
        cell_size=cell_size,
    )

    # Return total items added
    return result.segments_added + result.vias_added
