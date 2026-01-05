"""
KiCad PCB writer for exporting optimized placements.

This module provides functions to write optimized component placements back
to KiCad PCB files (.kicad_pcb) by updating component positions and rotations
while preserving all other design data (traces, zones, text, etc.).

Also provides functions for:
- Stripping traces/vias for unrouted benchmark comparisons
- Exporting placement-only PCBs
- Adding component bounding box visualization
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kiutils.board import Board as KiBoard
from kiutils.footprint import Footprint
from kiutils.items.common import Position
from kiutils.items.gritems import GrRect, GrText

from temper_placer.core.state import PlacementState


@dataclass
class WriteResult:
    """Result of writing placement to KiCad file."""

    output_path: Path
    components_updated: int
    components_skipped: int
    warnings: list[str]

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0


@dataclass
class StrippingResult:
    """Result of stripping routing from a KiCad file."""

    output_path: Path
    traces_removed: int
    vias_removed: int
    zones_removed: int
    components_preserved: int
    warnings: list[str]

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0


@dataclass
class PlacementUpdate:
    """
    Placement update for a single component.

    Attributes:
        ref: Component reference designator (e.g., "U1").
        x: New X position in mm.
        y: New Y position in mm.
        rotation: Rotation angle in degrees (0, 90, 180, or 270).
    """

    ref: str
    x: float
    y: float
    rotation: float  # degrees: 0, 90, 180, 270


def write_placements_to_pcb(
    template_pcb: Path,
    output_pcb: Path,
    placements: dict[str, PlacementUpdate],
    preserve_unmatched: bool = True,
) -> WriteResult:
    """
    Write optimized placements to a KiCad PCB file.

    This function:
    1. Loads the template PCB file
    2. Updates component positions and rotations for matched references
    3. Preserves all other design data (traces, zones, etc.)
    4. Writes the modified PCB to the output path

    Args:
        template_pcb: Path to the template .kicad_pcb file.
        output_pcb: Path for the output .kicad_pcb file.
        placements: Dictionary mapping component ref to PlacementUpdate.
        preserve_unmatched: If True, keep components not in placements dict
            at their original positions. If False, warn about unmatched.

    Returns:
        WriteResult with statistics and any warnings.
    """
    warnings: list[str] = []
    components_updated = 0
    components_skipped = 0

    # Load the template PCB
    try:
        ki_board = KiBoard.from_file(str(template_pcb))
    except Exception as e:
        raise ValueError(f"Failed to load template PCB: {e}")

    # Update footprint positions
    for fp in ki_board.footprints:
        ref = _get_footprint_reference(fp)
        if not ref:
            warnings.append(f"Skipping footprint with no reference: {fp.libId}")
            components_skipped += 1
            continue

        if ref not in placements:
            if not preserve_unmatched:
                warnings.append(f"Component {ref} not in placements, keeping original position")
            components_skipped += 1
            continue

        update = placements[ref]

        # Update position
        if fp.position is None:
            fp.position = Position(X=update.x, Y=update.y, angle=update.rotation)
        else:
            fp.position.X = update.x
            fp.position.Y = update.y
            fp.position.angle = update.rotation

        components_updated += 1

    # Ensure output directory exists
    output_pcb.parent.mkdir(parents=True, exist_ok=True)

    # Write the modified PCB
    try:
        ki_board.to_file(str(output_pcb))
    except Exception as e:
        raise ValueError(f"Failed to write output PCB: {e}")

    return WriteResult(
        output_path=output_pcb,
        components_updated=components_updated,
        components_skipped=components_skipped,
        warnings=warnings,
    )


def state_to_placements(
    state: PlacementState,
    component_refs: list[str],
    origin: tuple[float, float] = (0.0, 0.0),
    original_angles: dict[str, float] | None = None,
    components: list | None = None,
) -> dict[str, PlacementUpdate]:
    """
    Convert a PlacementState to placement updates.

    Args:
        state: The optimized PlacementState.
        component_refs: List of component reference designators, in the same
            order as state.positions.
        origin: (x, y) board origin to add to positions.
        original_angles: Optional dict mapping component ref to original angle
            in degrees. If provided, the rotation offset from the original
            angle to its quantized 90° value will be preserved in the output.
            This handles components with non-90° rotations gracefully.
        components: Optional list of Component objects. If provided, center
            offsets will be extracted and subtracted from positions to convert
            from bounding-box-center to footprint-origin coordinates.

    Returns:
        Dictionary mapping component ref to PlacementUpdate.
    """
    import math

    placements: dict[str, PlacementUpdate] = {}

    # Build center offset map from components if provided
    center_offsets: dict[str, tuple[float, float]] = {}
    if components:
        for comp in components:
            if hasattr(comp, "attributes") and comp.attributes:
                cx = float(comp.attributes.get("_center_offset_x", "0"))
                cy = float(comp.attributes.get("_center_offset_y", "0"))
                if cx != 0 or cy != 0:
                    center_offsets[comp.ref] = (cx, cy)

    # Get discrete rotations (to_discrete returns (positions, rotation_indices))
    _, rotation_indices = state.to_discrete()

    for i, ref in enumerate(component_refs):
        # Convert rotation index to degrees (0, 90, 180, 270)
        rotation_deg = float(rotation_indices[i]) * 90.0

        # If original angle was non-90°, preserve the offset
        # e.g., if original was 45° (quantized to 0°), and optimizer chose 90°,
        # output should be 90° + 45° = 135°
        if original_angles and ref in original_angles:
            original = original_angles[ref]
            quantized = round(original / 90) * 90.0
            offset = original - quantized
            if abs(offset) > 0.1:  # Only apply if there was a real offset
                rotation_deg = (rotation_deg + offset) % 360.0

        # Get position (internal bounding-box-center coordinates)
        x = float(state.positions[i, 0]) + origin[0]
        y = float(state.positions[i, 1]) + origin[1]

        # Subtract rotated center offset to convert to footprint origin
        if ref in center_offsets:
            cx, cy = center_offsets[ref]
            rot_rad = math.radians(rotation_deg)
            # Rotate the center offset by the final rotation
            rotated_cx = cx * math.cos(rot_rad) - cy * math.sin(rot_rad)
            rotated_cy = cx * math.sin(rot_rad) + cy * math.cos(rot_rad)
            x -= rotated_cx
            y -= rotated_cy

        placements[ref] = PlacementUpdate(
            ref=ref,
            x=x,
            y=y,
            rotation=rotation_deg,
        )

    return placements


def extract_original_angles(components: list) -> dict[str, float]:
    """
    Extract original angles from component attributes.

    This reads the '_original_angle' attribute stored by the parser
    for components with non-90° rotations.

    Args:
        components: List of Component objects from the netlist.

    Returns:
        Dictionary mapping component ref to original angle in degrees.
        Only includes components that had non-90° rotations.
    """
    angles: dict[str, float] = {}
    for comp in components:
        if hasattr(comp, "attributes") and "_original_angle" in comp.attributes:
            try:
                angles[comp.ref] = float(comp.attributes["_original_angle"])
            except (ValueError, TypeError):
                pass  # Skip invalid angle values
    return angles


def placements_to_json(placements: dict[str, PlacementUpdate]) -> dict:
    """
    Convert placements to a JSON-serializable dictionary.

    Args:
        placements: Dictionary of placement updates.

    Returns:
        Dictionary suitable for JSON serialization.
    """
    return {
        ref: {
            "x": update.x,
            "y": update.y,
            "rotation": update.rotation,
        }
        for ref, update in placements.items()
    }


def placements_from_json(data: dict) -> dict[str, PlacementUpdate]:
    """
    Load placements from a JSON-deserialized dictionary.

    Args:
        data: Dictionary from JSON.

    Returns:
        Dictionary of PlacementUpdate objects.
    """
    return {
        ref: PlacementUpdate(
            ref=ref,
            x=float(values["x"]),
            y=float(values["y"]),
            rotation=float(values["rotation"]),
        )
        for ref, values in data.items()
    }


def export_placements(
    template_pcb: Path,
    output_pcb: Path,
    state: PlacementState,
    component_refs: list[str],
    origin: tuple[float, float] = (0.0, 0.0),
    components: list | None = None,
) -> WriteResult:
    """
    High-level function to export optimized state to KiCad PCB.

    This is a convenience wrapper that combines state_to_placements and
    write_placements_to_pcb.

    Args:
        template_pcb: Path to the template .kicad_pcb file.
        output_pcb: Path for the output .kicad_pcb file.
        state: The optimized PlacementState.
        component_refs: List of component reference designators.
        origin: (x, y) board origin to add to positions.
        components: Optional list of Component objects for center offset correction.

    Returns:
        WriteResult with statistics and any warnings.
    """
    placements = state_to_placements(state, component_refs, origin, components=components)
    return write_placements_to_pcb(template_pcb, output_pcb, placements)


def _get_footprint_reference(fp: Footprint) -> str | None:
    """Extract reference designator from footprint."""
    # In kiutils, properties is a dict with key 'Reference'
    props = getattr(fp, "properties", {})
    if isinstance(props, dict):
        ref = props.get("Reference")
        if ref:
            return ref

    # Fall back to iterating if it's a list (older kiutils versions)
    if isinstance(props, list):
        for prop in props:
            if hasattr(prop, "key") and prop.key == "Reference":
                return prop.value

    # Try graphicItems (text items with reference type)
    for item in getattr(fp, "graphicItems", []):
        if hasattr(item, "type") and item.type == "reference":
            return getattr(item, "text", None)

    return None


def validate_output_pcb(output_pcb: Path) -> tuple[bool, list[str]]:
    """
    Validate that the output PCB file is readable.

    Args:
        output_pcb: Path to the PCB file to validate.

    Returns:
        Tuple of (is_valid, error_messages).
    """
    errors: list[str] = []

    if not output_pcb.exists():
        errors.append(f"Output file does not exist: {output_pcb}")
        return False, errors

    try:
        ki_board = KiBoard.from_file(str(output_pcb))
    except Exception as e:
        errors.append(f"Failed to parse output PCB: {e}")
        return False, errors

    # Basic sanity checks
    if not ki_board.footprints:
        errors.append("Output PCB has no footprints")
        return False, errors

    return True, []


def add_bounding_boxes_to_pcb(
    pcb_path: Path,
    component_bounds: dict[str, tuple[float, float, float, float]] | None = None,
    layer: str = "Dwgs.User",
    stroke_width: float = 0.2,
) -> int:
    """
    Add bounding box rectangles to a PCB file for component visualization.
    
    This draws a rectangle around each component on a user layer, making it
    easy to see component boundaries vs individual pads.
    
    If component_bounds is None, calculates bounds from actual footprint pads.
    
    Args:
        pcb_path: Path to the .kicad_pcb file to modify (in-place).
        component_bounds: Optional dict mapping ref -> (x, y, width, height).
            If None, bounds are calculated from footprint pads.
        layer: KiCad layer to draw on (default: "Dwgs.User").
        stroke_width: Line width in mm.
    
    Returns:
        Number of bounding boxes added.
    """
    import math
    
    try:
        ki_board = KiBoard.from_file(str(pcb_path))
    except Exception as e:
        raise ValueError(f"Failed to load PCB: {e}")
    
    boxes_added = 0
    
    for fp in ki_board.footprints:
        ref = _get_footprint_reference(fp)
        if not ref:
            continue
        
        # Get footprint center position
        fp_x = fp.position.X if fp.position else 0.0
        fp_y = fp.position.Y if fp.position else 0.0
        fp_angle = fp.position.angle if fp.position and fp.position.angle else 0.0
        angle_rad = math.radians(fp_angle)
        
        # Calculate bounds from all pads
        if not fp.pads:
            continue
            
        x_min, y_min = float('inf'), float('inf')
        x_max, y_max = float('-inf'), float('-inf')
        
        for pad in fp.pads:
            # Pad position is local to footprint center
            local_x = pad.position.X if pad.position else 0.0
            local_y = pad.position.Y if pad.position else 0.0
            
            # Rotate local position by footprint angle
            if abs(fp_angle) > 0.1:
                rotated_x = local_x * math.cos(angle_rad) - local_y * math.sin(angle_rad)
                rotated_y = local_x * math.sin(angle_rad) + local_y * math.cos(angle_rad)
            else:
                rotated_x, rotated_y = local_x, local_y
            
            # Get pad size
            pad_w = pad.size.X if pad.size else 1.0
            pad_h = pad.size.Y if pad.size else 1.0
            
            # Update bounds (absolute coordinates)
            abs_x = fp_x + rotated_x
            abs_y = fp_y + rotated_y
            
            x_min = min(x_min, abs_x - pad_w / 2)
            y_min = min(y_min, abs_y - pad_h / 2)
            x_max = max(x_max, abs_x + pad_w / 2)
            y_max = max(y_max, abs_y + pad_h / 2)
        
        # Add small margin
        margin = 0.3
        x_min -= margin
        y_min -= margin
        x_max += margin
        y_max += margin
        
        # Create rectangle graphic item
        try:
            rect = GrRect(
                start=Position(X=x_min, Y=y_min),
                end=Position(X=x_max, Y=y_max),
                layer=layer,
                width=stroke_width,
            )
            ki_board.graphicItems.append(rect)
            boxes_added += 1
        except Exception:
            # GrRect might not be available in older kiutils, skip silently
            pass
    
    # Write back
    try:
        ki_board.to_file(str(pcb_path))
    except Exception as e:
        raise ValueError(f"Failed to write PCB: {e}")
    
    return boxes_added


def add_silkscreen_labels(
    pcb_path: Path,
    add_references: bool = True,
    add_values: bool = True,
    add_fab_outlines: bool = True,
    text_height: float = 1.0,
    text_thickness: float = 0.15,
    outline_width: float = 0.15,
) -> dict[str, int]:
    """
    Add improved silkscreen labels and fab layer outlines to a PCB file.
    
    This function enhances component visibility by:
    1. Adding reference designators on F.SilkS layer (positioned above component)
    2. Adding value text on F.SilkS layer (positioned below reference)
    3. Adding component body outlines on F.Fab layer
    
    Args:
        pcb_path: Path to the .kicad_pcb file to modify (in-place).
        add_references: If True, add reference designator text.
        add_values: If True, add component value text.
        add_fab_outlines: If True, add F.Fab layer component outlines.
        text_height: Height of text in mm.
        text_thickness: Stroke width of text in mm.
        outline_width: Stroke width of F.Fab outlines in mm.
    
    Returns:
        Dictionary with counts: {"references": n, "values": n, "outlines": n}
    """
    import math
    
    try:
        ki_board = KiBoard.from_file(str(pcb_path))
    except Exception as e:
        raise ValueError(f"Failed to load PCB: {e}")
    
    counts = {"references": 0, "values": 0, "outlines": 0}
    
    for fp in ki_board.footprints:
        ref = _get_footprint_reference(fp)
        if not ref:
            continue
        
        # Get footprint position and bounds
        fp_x = fp.position.X if fp.position else 0.0
        fp_y = fp.position.Y if fp.position else 0.0
        fp_angle = fp.position.angle if fp.position and fp.position.angle else 0.0
        angle_rad = math.radians(fp_angle)
        
        # Calculate bounds from pads
        if not fp.pads:
            continue
            
        x_min, y_min = float('inf'), float('inf')
        x_max, y_max = float('-inf'), float('-inf')
        
        for pad in fp.pads:
            local_x = pad.position.X if pad.position else 0.0
            local_y = pad.position.Y if pad.position else 0.0
            
            if abs(fp_angle) > 0.1:
                rotated_x = local_x * math.cos(angle_rad) - local_y * math.sin(angle_rad)
                rotated_y = local_x * math.sin(angle_rad) + local_y * math.cos(angle_rad)
            else:
                rotated_x, rotated_y = local_x, local_y
            
            pad_w = pad.size.X if pad.size else 1.0
            pad_h = pad.size.Y if pad.size else 1.0
            
            abs_x = fp_x + rotated_x
            abs_y = fp_y + rotated_y
            
            x_min = min(x_min, abs_x - pad_w / 2)
            y_min = min(y_min, abs_y - pad_h / 2)
            x_max = max(x_max, abs_x + pad_w / 2)
            y_max = max(y_max, abs_y + pad_h / 2)
        
        comp_width = x_max - x_min
        comp_height = y_max - y_min
        comp_cx = (x_min + x_max) / 2
        comp_cy = (y_min + y_max) / 2
        
        # Scale text based on component size (min 0.8mm, max 1.5mm)
        scaled_height = max(0.8, min(1.5, min(comp_width, comp_height) / 4))
        
        # Get component value from properties
        value = None
        props = getattr(fp, "properties", {})
        if isinstance(props, dict):
            value = props.get("Value")
        elif isinstance(props, list):
            for prop in props:
                if hasattr(prop, "key") and prop.key == "Value":
                    value = getattr(prop, "value", None)
                    break
        
        # Add reference text on F.SilkS (positioned above component)
        if add_references:
            try:
                ref_y = y_min - scaled_height - 0.5  # Above component
                ref_text = GrText(
                    text=ref,
                    position=Position(X=comp_cx, Y=ref_y),
                    layer="F.SilkS",
                )
                # Set text attributes if available
                if hasattr(ref_text, "effects"):
                    pass  # Text effects handled differently in kiutils
                ki_board.graphicItems.append(ref_text)
                counts["references"] += 1
            except Exception:
                pass
        
        # Add value text on F.SilkS (positioned below reference)
        if add_values and value:
            try:
                val_y = y_min - 2 * scaled_height - 1.0  # Below reference
                val_text = GrText(
                    text=value,
                    position=Position(X=comp_cx, Y=val_y),
                    layer="F.SilkS",
                )
                ki_board.graphicItems.append(val_text)
                counts["values"] += 1
            except Exception:
                pass
        
        # Add F.Fab outline (component body rectangle)
        if add_fab_outlines:
            try:
                margin = 0.2
                fab_rect = GrRect(
                    start=Position(X=x_min - margin, Y=y_min - margin),
                    end=Position(X=x_max + margin, Y=y_max + margin),
                    layer="F.Fab",
                    width=outline_width,
                )
                ki_board.graphicItems.append(fab_rect)
                counts["outlines"] += 1
            except Exception:
                pass
    
    # Write back
    try:
        ki_board.to_file(str(pcb_path))
    except Exception as e:
        raise ValueError(f"Failed to write PCB: {e}")
    
    return counts


# ============================================================================
# Trace/Via Stripping for Unrouted Benchmarks
# ============================================================================


def strip_routing(
    input_pcb: Path,
    output_pcb: Path,
    keep_zones: bool = True,
    keep_fills: bool = False,
) -> StrippingResult:
    """
    Remove traces and vias from a KiCad PCB file while preserving components and netlist.

    This is used to create "unrouted" versions of PCBs for benchmark comparisons,
    where we want to compare optimizer placements against human placements without
    the interference of broken traces (which cause DRC errors when components move).

    What is REMOVED:
    - All trace segments on copper layers (F.Cu, B.Cu, In*.Cu)
    - All vias
    - Zone fills (optionally, if keep_fills=False)

    What is KEPT:
    - Footprints (components) with original positions
    - Pads and their net assignments (connectivity information)
    - Board outline (Edge.Cuts layer)
    - Text, silkscreen, labels
    - Design rules
    - Net definitions
    - Zone outlines (if keep_zones=True)

    Args:
        input_pcb: Path to the input .kicad_pcb file with routing.
        output_pcb: Path for the output .kicad_pcb file without routing.
        keep_zones: If True, keep zone outlines but remove fills.
                   If False, remove zones entirely.
        keep_fills: If True, keep zone copper fills (rarely desired).

    Returns:
        StrippingResult with statistics about what was removed.
    """
    warnings: list[str] = []
    traces_removed = 0
    vias_removed = 0
    zones_removed = 0

    # Load the input PCB
    try:
        ki_board = KiBoard.from_file(str(input_pcb))
    except Exception as e:
        raise ValueError(f"Failed to load input PCB: {e}")

    # Count components for verification
    components_preserved = len(ki_board.footprints)

    # Remove traces and vias from traceItems
    # traceItems contains: Segment (traces), Via, Arc
    original_trace_count = len(ki_board.traceItems) if ki_board.traceItems else 0

    # Filter traceItems - keep only non-routing items (there shouldn't be any)
    # In kiutils, traceItems are: Segment, Via, Arc
    if ki_board.traceItems:
        new_trace_items = []
        for item in ki_board.traceItems:
            item_type = type(item).__name__

            if item_type in ("Segment", "Arc"):
                # This is a trace segment - remove it
                traces_removed += 1
            elif item_type == "Via":
                # This is a via - remove it
                vias_removed += 1
            else:
                # Unknown type - keep it with warning
                warnings.append(f"Unknown traceItem type preserved: {item_type}")
                new_trace_items.append(item)

        ki_board.traceItems = new_trace_items

    # Handle zones
    if ki_board.zones:
        if not keep_zones:
            # Remove all zones entirely
            zones_removed = len(ki_board.zones)
            ki_board.zones = []
        elif not keep_fills:
            # Keep zone outlines but clear fills
            for zone in ki_board.zones:
                # Clear filled polygons (the copper pour)
                if hasattr(zone, "filledPolygons"):
                    zone.filledPolygons = []
                # The polygon/polygons attribute is the zone outline, keep it

    # Ensure output directory exists
    output_pcb.parent.mkdir(parents=True, exist_ok=True)

    # Write the stripped PCB
    try:
        ki_board.to_file(str(output_pcb))
    except Exception as e:
        raise ValueError(f"Failed to write output PCB: {e}")

    return StrippingResult(
        output_path=output_pcb,
        traces_removed=traces_removed,
        vias_removed=vias_removed,
        zones_removed=zones_removed,
        components_preserved=components_preserved,
        warnings=warnings,
    )


def strip_routing_preserve_nets(
    input_pcb: Path,
    output_pcb: Path,
) -> StrippingResult:
    """
    Strip routing with net assignment verification.

    This is a convenience wrapper around strip_routing that verifies
    net assignments are preserved after stripping.

    Args:
        input_pcb: Path to the input .kicad_pcb file.
        output_pcb: Path for the output .kicad_pcb file.

    Returns:
        StrippingResult with warnings if net assignments differ.
    """
    # First, capture net assignments from input
    try:
        ki_input = KiBoard.from_file(str(input_pcb))
    except Exception as e:
        raise ValueError(f"Failed to load input PCB: {e}")

    input_net_assignments: dict[str, dict[str, str]] = {}  # ref -> {pad_num -> net_name}
    for fp in ki_input.footprints:
        ref = _get_footprint_reference(fp)
        if ref:
            input_net_assignments[ref] = {}
            for pad in fp.pads:
                if pad.net and pad.net.name:
                    input_net_assignments[ref][pad.number or ""] = pad.net.name

    # Strip routing
    result = strip_routing(input_pcb, output_pcb, keep_zones=True, keep_fills=False)

    # Verify net assignments in output
    try:
        ki_output = KiBoard.from_file(str(output_pcb))
    except Exception as e:
        result.warnings.append(f"Failed to verify output: {e}")
        return result

    for fp in ki_output.footprints:
        ref = _get_footprint_reference(fp)
        if ref and ref in input_net_assignments:
            for pad in fp.pads:
                pad_num = pad.number or ""
                expected_net = input_net_assignments[ref].get(pad_num)
                actual_net = pad.net.name if pad.net else None
                if expected_net == actual_net:
                    continue
                if expected_net and actual_net != expected_net:
                    result.warnings.append(
                        f"Net assignment mismatch for {ref} pad {pad_num}: expected {expected_net}, got {actual_net}"
                    )

    return result


# ============================================================================
# Route Export for Deterministic Pipeline
# ============================================================================


def write_routes_to_pcb(
    template_pcb: Path,
    output_pcb: Path,
    routes: frozenset,
    net_name_to_index: dict[str, int] | None = None,
    clear_existing: bool = False,
) -> WriteResult:
    """
    Add deterministic routes (traces) to a KiCad PCB file.
    
    This function takes routes generated by the deterministic pipeline
    (as Trace objects) and adds them to a KiCad board as Segment objects.
    
    Args:
        template_pcb: Path to the template .kicad_pcb file.
        output_pcb: Path for the output .kicad_pcb file.
        routes: Frozen set of Trace objects from BoardState.routes.
        net_name_to_index: Optional map of net name → net index.
            If None, will be built from the template PCB.
        clear_existing: If True, remove all existing traces before adding new ones.
    
    Returns:
        WriteResult with statistics and warnings.
    """
    from kiutils.items.common import Position
    from kiutils.items.track import Segment
    
    warnings: list[str] = []
    traces_added = 0
    traces_skipped = 0
    
    # Load the template PCB
    try:
        ki_board = KiBoard.from_file(str(template_pcb))
    except Exception as e:
        raise ValueError(f"Failed to load template PCB: {e}")
    
    # Build net name → index mapping if not provided
    if net_name_to_index is None:
        net_name_to_index = {}
        if hasattr(ki_board, 'nets') and ki_board.nets:
            for net in ki_board.nets:
                if hasattr(net, 'name') and hasattr(net, 'number'):
                    net_name_to_index[net.name] = net.number
    
    # Clear existing traces if requested
    if clear_existing and hasattr(ki_board, 'traceItems'):
        original_count = len(ki_board.traceItems) if ki_board.traceItems else 0
        ki_board.traceItems = []
        if original_count > 0:
            warnings.append(f"Cleared {original_count} existing trace items")
    
    # Initialize traceItems if it doesn't exist
    if not hasattr(ki_board, 'traceItems') or ki_board.traceItems is None:
        ki_board.traceItems = []
    
    # Add routes as Segment objects
    for route in routes:
        # Get net index (default to 0 if not found)
        net_index = 0
        if route.net and route.net in net_name_to_index:
            net_index = net_name_to_index[route.net]
        elif route.net:
            warnings.append(f"Net '{route.net}' not found in board, using index 0")
        
        try:
            segment = Segment(
                start=Position(X=route.start[0], Y=route.start[1]),
                end=Position(X=route.end[0], Y=route.end[1]),
                width=route.width,
                layer=route.layer,
                net=net_index,
            )
            ki_board.traceItems.append(segment)
            traces_added += 1
        except Exception as e:
            warnings.append(f"Failed to add trace {route.start} → {route.end}: {e}")
            traces_skipped += 1
    
    # Ensure output directory exists
    output_pcb.parent.mkdir(parents=True, exist_ok=True)
    
    # Write the modified PCB
    try:
        ki_board.to_file(str(output_pcb))
    except Exception as e:
        raise ValueError(f"Failed to write output PCB: {e}")
    
    return WriteResult(
        output_path=output_pcb,
        components_updated=traces_added,  # Reusing field for trace count
        components_skipped=traces_skipped,
        warnings=warnings,
    )


def build_net_name_to_index_map(pcb_path: Path) -> dict[str, int]:
    """
    Extract net name → index mapping from a KiCad PCB file.
    
    KiCad uses integer net indices internally, but our Trace objects
    use net names. This function builds the mapping for conversion.
    
    Args:
        pcb_path: Path to .kicad_pcb file.
    
    Returns:
        Dictionary mapping net name (str) to net index (int).
    """
    try:
        ki_board = KiBoard.from_file(str(pcb_path))
    except Exception as e:
        raise ValueError(f"Failed to load PCB: {e}")
    
    net_map = {}
    if hasattr(ki_board, 'nets') and ki_board.nets:
        for net in ki_board.nets:
            if hasattr(net, 'name') and hasattr(net, 'number'):
                net_map[net.name] = net.number
    
    return net_map


def get_routing_statistics(pcb_path: Path) -> dict[str, int]:
    """
    Get statistics about routing in a PCB file.

    Args:
        pcb_path: Path to the .kicad_pcb file.

    Returns:
        Dictionary with counts of traces, vias, zones, components.
    """
    try:
        ki_board = KiBoard.from_file(str(pcb_path))
    except Exception as e:
        raise ValueError(f"Failed to load PCB: {e}")

    trace_count = 0
    via_count = 0

    if ki_board.traceItems:
        for item in ki_board.traceItems:
            item_type = type(item).__name__
            if item_type in ("Segment", "Arc"):
                trace_count += 1
            elif item_type == "Via":
                via_count += 1

    return {
        "traces": trace_count,
        "vias": via_count,
        "zones": len(ki_board.zones) if ki_board.zones else 0,
        "components": len(ki_board.footprints) if ki_board.footprints else 0,
        "nets": len(ki_board.nets) if ki_board.nets else 0,
    }
