"""Internal: board-level placement serialization and isolation slot functions."""

from __future__ import annotations

import contextlib
import math
from pathlib import Path

from kiutils.board import Board as KiBoard
from kiutils.items.common import Position
from kiutils.items.gritems import GrLine

from temper_placer.core.state import PlacementState
from temper_placer.io._write_types import (
    IsolationSlotResult,
    PlacementUpdate,
    WriteResult,
    _get_footprint_reference,
)
from temper_placer.io.kicad_exporter import _validate_4_layer_output


def _reorient_pads(fp, old_fp_angle: float, new_fp_angle: float) -> None:
    """Rotate a footprint's pad *bodies* to match its new board rotation.

    In a ``.kicad_pcb`` file a pad's ``(at x y angle)`` angle is the pad's
    **absolute** (world) orientation, not an offset from the parent
    footprint's angle -- KiCad's parser does not add the footprint angle to
    it. So changing ``footprint.at`` rotation moves every pad's *position*
    (KiCad rotates ``at`` offsets at load time) but leaves every pad *body*
    pointing the way it did before, unless the pad angles are rewritten too.

    Failing to rewrite them silently squashes fine-pitch packages: an
    SSOP-20 rotated 270 degrees keeps 1.2mm-long pad bodies lying along the
    0.635mm pitch axis, so every adjacent pad pair physically overlaps and
    KiCad reports ``shorting_items``. Measured on ``pcb/temper.kicad_pcb``:
    55 of 60 intra-component shorts, plus 76 solder-mask bridges and 93
    ``lib_footprint_mismatch`` violations, all from this one omission. See
    ``docs/evidence/2026-07-29-intra-component-shorts-root-cause.md``.

    Each pad's *intrinsic* orientation (its angle relative to its parent, as
    defined by the library footprint) is preserved: ``intrinsic =
    old_pad_angle - old_fp_angle``, and the new absolute angle is
    ``new_fp_angle + intrinsic``.
    """
    delta = new_fp_angle - old_fp_angle
    if delta % 360.0 == 0.0:
        return
    for pad in fp.pads or []:
        if pad.position is None:
            continue
        current = pad.position.angle or 0.0
        new_angle = (current + delta) % 360.0
        # kiutils omits the angle token when it is None; an absent angle
        # means 0 in KiCad, so only write None when the result really is 0.
        pad.position.angle = None if new_angle == 0.0 else new_angle


def write_placements_to_pcb(
    template_pcb: Path,
    output_pcb: Path,
    placements: dict[str, PlacementUpdate],
    preserve_unmatched: bool = True,
    components: list | None = None,
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
            Positions are assumed to be in bounding-box-center coordinates
            if `components` is provided, otherwise footprint-origin coordinates.
        preserve_unmatched: If True, keep components not in placements dict
            at their original positions. If False, warn about unmatched.
        components: Optional list of Component objects from the netlist.
            If provided, center offsets will be extracted and subtracted
            from positions to convert from bounding-box-center to
            footprint-origin coordinates (which KiCad expects).

    Returns:
        WriteResult with statistics and any warnings.
    """
    warnings: list[str] = []
    components_updated = 0
    components_skipped = 0

    # Build center offset map from components if provided
    center_offsets: dict[str, tuple[float, float]] = {}
    if components:
        for comp in components:
            if hasattr(comp, "attributes") and comp.attributes:
                cx = float(comp.attributes.get("_center_offset_x", "0"))
                cy = float(comp.attributes.get("_center_offset_y", "0"))
                if cx != 0 or cy != 0:
                    center_offsets[comp.ref] = (cx, cy)

    # Load the template PCB
    try:
        ki_board = KiBoard.from_file(str(template_pcb))
    except Exception as e:
        raise ValueError(f"Failed to load template PCB: {e}") from e

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
        x, y = update.x, update.y
        rotation_deg = update.rotation

        # Convert from bounding-box-center to footprint-origin coordinates
        if ref in center_offsets:
            cx, cy = center_offsets[ref]
            rot_rad = math.radians(rotation_deg)
            # Rotate the center offset by the component's rotation. KiCad's
            # real convention is R(-theta), not R(+theta) -- confirmed
            # against real kicad-cli 10.0.4 pcb drc ground truth, see
            # docs/evidence/2026-07-29-cross-domain-creepage-rotation-convention.md
            # Sec. 2. Must match the parser's inverse (io/_parse_modules.py)
            # for this writer to place the footprint anchor where the
            # parser's center actually resolves to.
            rotated_cx = cx * math.cos(rot_rad) + cy * math.sin(rot_rad)
            rotated_cy = -cx * math.sin(rot_rad) + cy * math.cos(rot_rad)
            x -= rotated_cx
            y -= rotated_cy

        # Update position. Pad bodies must be re-oriented alongside the
        # footprint: a .kicad_pcb pad angle is absolute, so rotating only the
        # footprint leaves every pad body unrotated (see _reorient_pads).
        if fp.position is None:
            fp.position = Position(X=x, Y=y, angle=rotation_deg)
            _reorient_pads(fp, 0.0, rotation_deg)
        else:
            old_angle = fp.position.angle or 0.0
            fp.position.X = x
            fp.position.Y = y
            fp.position.angle = rotation_deg
            _reorient_pads(fp, old_angle, rotation_deg)

        components_updated += 1

    # Ensure output directory exists
    output_pcb.parent.mkdir(parents=True, exist_ok=True)

    # Write the modified PCB
    try:
        _validate_4_layer_output(ki_board)
        ki_board.to_file(str(output_pcb))
    except Exception as e:
        raise ValueError(f"Failed to write output PCB: {e}") from e

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
            # Rotate the center offset by the final rotation. KiCad's real
            # convention is R(-theta), not R(+theta) -- see
            # docs/evidence/2026-07-29-cross-domain-creepage-rotation-convention.md
            # Sec. 2. Must match the parser's inverse (io/_parse_modules.py).
            rotated_cx = cx * math.cos(rot_rad) + cy * math.sin(rot_rad)
            rotated_cy = -cx * math.sin(rot_rad) + cy * math.cos(rot_rad)
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
            with contextlib.suppress(ValueError, TypeError):
                angles[comp.ref] = float(comp.attributes["_original_angle"])
    return angles


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


def add_isolation_slots_to_pcb(
    pcb_path: Path,
    isolation_slots: list,
    output_path: Path | None = None,
) -> IsolationSlotResult:
    """
    Add creepage isolation slots to a KiCad PCB file.

    Slots are drawn on the Edge.Cuts layer as lines with specified width.
    The PCB manufacturer will route these as slots (board cutouts).

    For TO-247 packages where gate pin is 5.45mm from HV collector:
    - A 1.5mm wide slot between pins forces creepage path around it
    - Effective creepage becomes 12-15mm (compliant with IEC 60335-1's 6mm requirement)

    Args:
        pcb_path: Path to the input .kicad_pcb file.
        isolation_slots: List of IsolationSlot objects from config.
        output_path: Optional output path. If None, modifies pcb_path in-place.

    Returns:
        IsolationSlotResult with statistics and warnings.

    Example config YAML:
        isolation_slots:
          - name: "q1_gate_isolation"
            component_ref: "Q1"
            start_offset: [-2.0, -2.5]   # Relative to component center
            end_offset: [-2.0, 7.5]      # Slot runs vertically
            width_mm: 1.5
            lv_pin: "1"                  # Gate
            hv_pin: "2"                  # Collector
            description: "IEC 60335-1 creepage isolation"
    """
    warnings: list[str] = []
    slots_added = 0
    slots_skipped = 0

    # Load the PCB
    try:
        ki_board = KiBoard.from_file(str(pcb_path))
    except Exception as e:
        raise ValueError(f"Failed to load PCB: {e}") from e

    # Build component reference -> position mapping
    component_positions: dict[str, tuple[float, float, float]] = {}  # ref -> (x, y, angle)
    for fp in ki_board.footprints:
        ref = _get_footprint_reference(fp)
        if ref and fp.position:
            x = fp.position.X if fp.position.X is not None else 0.0
            y = fp.position.Y if fp.position.Y is not None else 0.0
            angle = fp.position.angle if fp.position.angle is not None else 0.0
            component_positions[ref] = (x, y, angle)

    # Add slots for each IsolationSlot configuration
    for slot in isolation_slots:
        comp_ref = slot.component_ref

        if comp_ref not in component_positions:
            warnings.append(f"Component '{comp_ref}' not found for slot '{slot.name}'")
            slots_skipped += 1
            continue

        comp_x, comp_y, comp_angle = component_positions[comp_ref]
        angle_rad = math.radians(comp_angle)

        # Get slot offsets from component origin
        dx_start, dy_start = slot.start_offset
        dx_end, dy_end = slot.end_offset

        # Rotate offsets by component angle. KiCad's real convention is
        # R(-theta), not R(+theta) -- see
        # docs/evidence/2026-07-29-cross-domain-creepage-rotation-convention.md
        # Sec. 2.
        # Note: Apply rotation for any non-zero angle (threshold removed to avoid
        # silently ignoring small rotations that could affect slot placement)
        if comp_angle != 0.0:
            rot_start_x = dx_start * math.cos(angle_rad) + dy_start * math.sin(angle_rad)
            rot_start_y = -dx_start * math.sin(angle_rad) + dy_start * math.cos(angle_rad)
            rot_end_x = dx_end * math.cos(angle_rad) + dy_end * math.sin(angle_rad)
            rot_end_y = -dx_end * math.sin(angle_rad) + dy_end * math.cos(angle_rad)
        else:
            rot_start_x, rot_start_y = dx_start, dy_start
            rot_end_x, rot_end_y = dx_end, dy_end

        # Absolute coordinates
        abs_start_x = comp_x + rot_start_x
        abs_start_y = comp_y + rot_start_y
        abs_end_x = comp_x + rot_end_x
        abs_end_y = comp_y + rot_end_y

        # Create GrLine on Edge.Cuts layer
        # Width of the line = slot width (routed slot)
        try:
            slot_line = GrLine(
                start=Position(X=abs_start_x, Y=abs_start_y),
                end=Position(X=abs_end_x, Y=abs_end_y),
                layer="Edge.Cuts",
                width=slot.width_mm,
            )
            ki_board.graphicItems.append(slot_line)
            slots_added += 1
        except Exception as e:
            warnings.append(f"Failed to add slot '{slot.name}': {e}")
            slots_skipped += 1

    # Write output
    out_path = output_path if output_path else pcb_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        _validate_4_layer_output(ki_board)
        ki_board.to_file(str(out_path))
    except Exception as e:
        raise ValueError(f"Failed to write PCB: {e}") from e

    return IsolationSlotResult(
        output_path=out_path,
        slots_added=slots_added,
        slots_skipped=slots_skipped,
        warnings=warnings,
    )


def compute_to247_isolation_slots(
    component_refs: list[str],
    slot_width_mm: float = 1.5,
    slot_length_mm: float = 10.0,
) -> list:
    """
    Automatically compute isolation slot positions for TO-247 packages.

    TO-247 packages have a fixed geometry where pin 1 (gate) is 5.45mm
    from pin 2 (collector/drain). This function computes slot positions
    that isolate the gate from HV pins.

    The slot is positioned between pin 1 and pin 2, running perpendicular
    to the pin row to maximize creepage path extension.

    Args:
        component_refs: List of component references to add slots for (e.g., ["Q1", "Q2"]).
        slot_width_mm: Width of the slot (default 1.5mm).
        slot_length_mm: Length of the slot (default 10mm).

    Returns:
        List of IsolationSlot objects ready for use with add_isolation_slots_to_pcb().
    """
    from temper_placer.io.config_loader import IsolationSlot

    # TO-247 pin geometry (from datasheet, pin 1 to pin 2 center-to-center)
    # Pin pitch: 5.45mm between pin 1 and pin 2
    # Pins are aligned along the X-axis when component angle=0
    TO247_PIN1_TO_PIN2_X = 5.45  # mm

    # Slot position: between pin 1 and pin 2, offset to avoid hitting pads
    # Place slot at X = 2.72mm (midpoint) from component origin (which is typically at pin 2)
    SLOT_X_OFFSET = -TO247_PIN1_TO_PIN2_X / 2  # Between pins

    slots = []
    for ref in component_refs:
        # Create slot definition
        # Slot runs vertically (Y direction) centered on the midpoint between pins
        slot = IsolationSlot(
            name=f"{ref.lower()}_gate_isolation",
            component_ref=ref,
            start_offset=(SLOT_X_OFFSET, -slot_length_mm / 2),
            end_offset=(SLOT_X_OFFSET, slot_length_mm / 2),
            width_mm=slot_width_mm,
            lv_pin="1",  # Gate
            hv_pin="2",  # Collector/Drain
            description=f"IEC 60335-1 creepage isolation for {ref} gate",
        )
        slots.append(slot)

    return slots
