"""Internal: board-level placement serialization and isolation slot functions.

kiutils-free (Wave 4 Phase 3, formats/IO): board I/O goes through the
Rust parse engine's text path — ``update_footprint_positions_py``
updates footprint ``(at ...)`` nodes and reorients pad angles in the
KiNode tree; ``extract_footprint_info_py`` reads footprint positions;
``gr_line_sexpr_py`` constructs isolation slot s-expressions; and
``append_items_to_board_py`` inserts items into the tree and serializes
back to text. No kiutils ``Board`` object is loaded or mutated.
"""

from __future__ import annotations

import contextlib
import math
from pathlib import Path

import temper_design_bundle_python as _tdb
from temper_io_types import kicad_write_geometry as _GEOM

from temper_placer.core.state import PlacementState
from temper_placer.geometry.kicad_transform import rotate_local_to_world
from temper_placer.io._write_types import (
    IsolationSlotResult,
    PlacementUpdate,
    WriteResult,
)


def write_placements_to_pcb(
    template_pcb: Path,
    output_pcb: Path,
    placements: dict[str, PlacementUpdate],
    preserve_unmatched: bool = True,
    components: list | None = None,
    board_origin: tuple[float, float] = (0.0, 0.0),
) -> WriteResult:
    """
    Write optimized placements to a KiCad PCB file.

    See the pre-migration docstring for the full board-origin and
    center-offset rationale. The Rust kernel
    ``update_footprint_positions_py`` finds each footprint by Reference
    property, updates its ``(at X Y angle)`` node, and reorients pad
    angles by ``delta = new_angle - old_angle`` (preserving each pad's
    intrinsic orientation relative to its parent).
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

    content = Path(template_pcb).read_text(encoding="utf-8")

    # Build the placement tuples for the Rust kernel
    placement_tuples: list[tuple[str, float, float, float]] = []
    for fp_info in _tdb.parse_engine.extract_footprint_info_py(content):
        ref = fp_info["ref"]
        if not ref:
            components_skipped += 1
            continue

        if ref not in placements:
            if not preserve_unmatched:
                warnings.append(f"Component {ref} not in placements, keeping original position")
            components_skipped += 1
            continue

        update = placements[ref]
        x, y = update.x, update.y
        x += board_origin[0]
        y += board_origin[1]
        rotation_deg = update.rotation

        # Convert from bounding-box-center to footprint-origin coordinates
        if ref in center_offsets:
            cx, cy = center_offsets[ref]
            rot_rad = math.radians(rotation_deg)
            rotated_cx, rotated_cy = rotate_local_to_world(cx, cy, rot_rad)
            x -= rotated_cx
            y -= rotated_cy

        placement_tuples.append((ref, x, y, rotation_deg))
        components_updated += 1

    result_text = _tdb.parse_engine.update_footprint_positions_py(content, placement_tuples)

    output_pcb.parent.mkdir(parents=True, exist_ok=True)
    output_pcb.write_text(result_text, encoding="utf-8")

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

    Pure data transform — no kiutils dependency. See the pre-migration
    docstring for the full rationale.
    """
    placements: dict[str, PlacementUpdate] = {}

    center_offsets: dict[str, tuple[float, float]] = {}
    if components:
        for comp in components:
            if hasattr(comp, "attributes") and comp.attributes:
                cx = float(comp.attributes.get("_center_offset_x", "0"))
                cy = float(comp.attributes.get("_center_offset_y", "0"))
                if cx != 0 or cy != 0:
                    center_offsets[comp.ref] = (cx, cy)

    _, rotation_indices = state.to_discrete()

    for i, ref in enumerate(component_refs):
        rotation_deg = float(rotation_indices[i]) * 90.0

        if original_angles and ref in original_angles:
            from temper_design_bundle_python import (
                write_board_geometry as _write_board_geometry,
            )

            rotation_deg = _write_board_geometry.preserve_rotation_offset_py(
                rotation_deg, original_angles[ref]
            )

        x = float(state.positions[i, 0]) + origin[0]
        y = float(state.positions[i, 1]) + origin[1]

        if ref in center_offsets:
            cx, cy = center_offsets[ref]
            rot_rad = math.radians(rotation_deg)
            rotated_cx, rotated_cy = rotate_local_to_world(cx, cy, rot_rad)
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

    Pure data transform — no kiutils dependency.
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

    Convenience wrapper combining state_to_placements and
    write_placements_to_pcb.
    """
    placements = state_to_placements(state, component_refs, origin, components=components)
    return write_placements_to_pcb(template_pcb, output_pcb, placements)


def validate_output_pcb(output_pcb: Path) -> tuple[bool, list[str]]:
    """
    Validate that the output PCB file is readable.

    Uses the Rust parse engine to verify the board is parseable and
    has footprints.
    """
    errors: list[str] = []

    if not output_pcb.exists():
        errors.append(f"Output file does not exist: {output_pcb}")
        return False, errors

    try:
        content = output_pcb.read_text(encoding="utf-8")
        footprints = _tdb.parse_engine.extract_footprint_info_py(content)
        if not footprints:
            errors.append("Output PCB has no footprints")
            return False, errors
    except Exception as e:
        errors.append(f"Failed to parse output PCB: {e}")
        return False, errors

    return True, []


def add_isolation_slots_to_pcb(
    pcb_path: Path,
    isolation_slots: list,
    output_path: Path | None = None,
) -> IsolationSlotResult:
    """
    Add creepage isolation slots to a KiCad PCB file.

    See the pre-migration docstring for the full TO-247 isolation slot
    rationale. The Rust kernels ``extract_footprint_info_py`` (positions)
    and ``gr_line_sexpr_py`` (s-expr construction) plus
    ``append_items_to_board_py`` (tree insertion) replace kiutils.
    """
    warnings: list[str] = []
    slots_added = 0
    slots_skipped = 0

    content = Path(pcb_path).read_text(encoding="utf-8")

    # Build component reference → position mapping
    footprints = _tdb.parse_engine.extract_footprint_info_py(content)
    component_positions: dict[str, tuple[float, float, float]] = {}
    for fp in footprints:
        ref = fp["ref"]
        if ref:
            component_positions[ref] = (fp["x"], fp["y"], fp["angle"])

    item_sexprs: list = []

    for slot in isolation_slots:
        comp_ref = slot.component_ref

        if comp_ref not in component_positions:
            warnings.append(f"Component '{comp_ref}' not found for slot '{slot.name}'")
            slots_skipped += 1
            continue

        comp_x, comp_y, comp_angle = component_positions[comp_ref]
        angle_rad = math.radians(comp_angle)

        dx_start, dy_start = slot.start_offset
        dx_end, dy_end = slot.end_offset

        if comp_angle != 0.0:
            rot_start_x, rot_start_y = rotate_local_to_world(dx_start, dy_start, angle_rad)
            rot_end_x, rot_end_y = rotate_local_to_world(dx_end, dy_end, angle_rad)
        else:
            rot_start_x, rot_start_y = dx_start, dy_start
            rot_end_x, rot_end_y = dx_end, dy_end

        abs_start_x = comp_x + rot_start_x
        abs_start_y = comp_y + rot_start_y
        abs_end_x = comp_x + rot_end_x
        abs_end_y = comp_y + rot_end_y

        try:
            item_sexprs.append(
                _GEOM.gr_line_sexpr_py(
                    abs_start_x, abs_start_y, abs_end_x, abs_end_y, "Edge.Cuts", slot.width_mm
                )
            )
            slots_added += 1
        except Exception as e:
            warnings.append(f"Failed to add slot '{slot.name}': {e}")
            slots_skipped += 1

    result_text = _tdb.parse_engine.append_items_to_board_py(content, item_sexprs)

    out_path = output_path if output_path else pcb_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(result_text, encoding="utf-8")

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

    Pure data transform — no kiutils dependency. See the pre-migration
    docstring for the TO-247 pin geometry rationale.
    """
    from temper_placer.io.config_loader import IsolationSlot

    TO247_PIN1_TO_PIN2_X = 5.45

    SLOT_X_OFFSET = -TO247_PIN1_TO_PIN2_X / 2

    slots = []
    for ref in component_refs:
        slot = IsolationSlot(
            name=f"{ref.lower()}_gate_isolation",
            component_ref=ref,
            start_offset=(SLOT_X_OFFSET, -slot_length_mm / 2),
            end_offset=(SLOT_X_OFFSET, slot_length_mm / 2),
            width_mm=slot_width_mm,
            lv_pin="1",
            hv_pin="2",
            description=f"IEC 60335-1 creepage isolation for {ref} gate",
        )
        slots.append(slot)

    return slots
