"""
KiCad PCB writer for exporting optimized placements.

This module provides functions to write optimized component placements back
to KiCad PCB files (.kicad_pcb) by updating component positions and rotations
while preserving all other design data (traces, zones, text, etc.).
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
) -> Dict[str, PlacementUpdate]:
    """
    Convert a PlacementState to placement updates.

    Args:
        state: The optimized PlacementState.
        component_refs: List of component reference designators, in the same
            order as state.positions.
        origin: (x, y) board origin to add to positions.

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

        placements[ref] = PlacementUpdate(
            ref=ref,
            x=x,
            y=y,
            rotation=rotation_deg,
        )

    return placements


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
