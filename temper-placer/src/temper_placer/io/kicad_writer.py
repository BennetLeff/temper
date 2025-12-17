"""
KiCad PCB writer for exporting optimized placements.

This module provides functions to write optimized component placements back
to KiCad PCB files (.kicad_pcb) by updating component positions and rotations
while preserving all other design data (traces, zones, text, etc.).

Also provides functions for:
- Stripping traces/vias for unrouted benchmark comparisons
- Exporting placement-only PCBs
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from kiutils.board import Board as KiBoard
from kiutils.footprint import Footprint
from kiutils.items.common import Position

from temper_placer.core.state import PlacementState


@dataclass
class WriteResult:
    """Result of writing placement to KiCad file."""

    output_path: Path
    components_updated: int
    components_skipped: int
    warnings: List[str]

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
    warnings: List[str]

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
    placements: Dict[str, PlacementUpdate],
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
    warnings: List[str] = []
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
    component_refs: List[str],
    origin: Tuple[float, float] = (0.0, 0.0),
    original_angles: Optional[Dict[str, float]] = None,
) -> Dict[str, PlacementUpdate]:
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

    Returns:
        Dictionary mapping component ref to PlacementUpdate.
    """
    placements: Dict[str, PlacementUpdate] = {}

    # Get discrete rotations (to_discrete returns (positions, rotation_indices))
    _, rotation_indices = state.to_discrete()

    for i, ref in enumerate(component_refs):
        # Get position (add origin offset)
        x = float(state.positions[i, 0]) + origin[0]
        y = float(state.positions[i, 1]) + origin[1]

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

        placements[ref] = PlacementUpdate(
            ref=ref,
            x=x,
            y=y,
            rotation=rotation_deg,
        )

    return placements


def extract_original_angles(components: List) -> Dict[str, float]:
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
    angles: Dict[str, float] = {}
    for comp in components:
        if hasattr(comp, "attributes") and "_original_angle" in comp.attributes:
            try:
                angles[comp.ref] = float(comp.attributes["_original_angle"])
            except (ValueError, TypeError):
                pass  # Skip invalid angle values
    return angles


def placements_to_json(placements: Dict[str, PlacementUpdate]) -> Dict:
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


def placements_from_json(data: Dict) -> Dict[str, PlacementUpdate]:
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
    component_refs: List[str],
    origin: Tuple[float, float] = (0.0, 0.0),
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

    Returns:
        WriteResult with statistics and any warnings.
    """
    placements = state_to_placements(state, component_refs, origin)
    return write_placements_to_pcb(template_pcb, output_pcb, placements)


def _get_footprint_reference(fp: Footprint) -> Optional[str]:
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


def validate_output_pcb(output_pcb: Path) -> Tuple[bool, List[str]]:
    """
    Validate that the output PCB file is readable.

    Args:
        output_pcb: Path to the PCB file to validate.

    Returns:
        Tuple of (is_valid, error_messages).
    """
    errors: List[str] = []

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
    warnings: List[str] = []
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

    input_net_assignments: Dict[str, Dict[str, str]] = {}  # ref -> {pad_num -> net_name}
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

                if expected_net != actual_net:
                    result.warnings.append(
                        f"Net mismatch for {ref}.{pad_num}: "
                        f"expected '{expected_net}', got '{actual_net}'"
                    )

    return result


def get_routing_statistics(pcb_path: Path) -> Dict[str, int]:
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
