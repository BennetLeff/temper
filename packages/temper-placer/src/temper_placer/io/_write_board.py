"""Internal: board-level placement serialization and isolation slot functions.

Wave 4, Phase 3, candidate 4: the placement math (center-offset rotation,
discrete rotations, pad re-orientation, slot geometry) delegates to the
``temper-io-types`` ``kicad_write`` kernels. This shim keeps the kiutils
board I/O (``KiBoard.from_file`` / ``board.to_file``) and item construction
(``Position`` / ``GrLine``) across the boundary.
"""

from __future__ import annotations

from pathlib import Path

from kiutils.board import Board as KiBoard
from kiutils.items.common import Position
from kiutils.items.gritems import GrLine

from temper_io_types import (
    add_isolation_slots_plan,
    compute_to247_isolation_slots as _rs_compute_to247_isolation_slots,
    extract_center_offsets,
    extract_original_angles as _rs_extract_original_angles,
    reorient_pad_angle,
    state_to_placements as _rs_state_to_placements,
    write_placements_plan,
)

from temper_placer.core.state import PlacementState
from temper_placer.io._write_types import (
    IsolationSlotResult,
    PlacementUpdate,
    WriteResult,
)
from temper_placer.io.kicad_exporter import _validate_4_layer_output


def _reorient_pads(fp, old_fp_angle: float, new_fp_angle: float) -> None:
    """Rotate a footprint's pad *bodies* to match its new board rotation.

    The per-pad angle math is the ``temper-io-types`` ``reorient_pad_angle``
    kernel; the kiutils object mutation (``pad.position.angle``) stays here.
    """
    delta = new_fp_angle - old_fp_angle
    if delta % 360.0 == 0.0:
        return
    for pad in fp.pads or []:
        if pad.position is None:
            continue
        current = pad.position.angle or 0.0
        # kiutils omits the angle token when it is None; an absent angle
        # means 0 in KiCad, so only write None when the result really is 0.
        pad.position.angle = reorient_pad_angle(current, delta)


def write_placements_to_pcb(
    template_pcb: Path,
    output_pcb: Path,
    placements: dict[str, PlacementUpdate],
    preserve_unmatched: bool = True,
    components: list | None = None,
) -> WriteResult:
    """
    Write optimized placements to a KiCad PCB file.

    The center-offset math, per-footprint match/skip decisions, position
    computation and pad re-orientation plan run in the ``temper-io-types``
    ``write_placements_plan`` kernel; this shim applies the returned plan to
    the kiutils board and serializes.
    """
    warnings: list[str] = []
    components_updated = 0
    components_skipped = 0

    # Load the template PCB
    try:
        ki_board = KiBoard.from_file(str(template_pcb))
    except Exception as e:
        raise ValueError(f"Failed to load template PCB: {e}") from e

    updates, components_updated, components_skipped, warnings = write_placements_plan(
        placements, components, ki_board.footprints, preserve_unmatched
    )

    # Apply the plan to the kiutils board (thin attribute plumbing).
    for update in updates:
        fp_index, ref, x, y, rotation_deg, had_position, pad_updates = update
        fp = ki_board.footprints[fp_index]
        if had_position:
            fp.position.X = x
            fp.position.Y = y
            fp.position.angle = rotation_deg
        else:
            fp.position = Position(X=x, Y=y, angle=rotation_deg)
        for pad_index, new_angle in pad_updates:
            fp.pads[pad_index].position.angle = new_angle

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

    The numpy-backed state surface (``state.positions`` indexing,
    ``state.to_discrete()``) is extracted here; the rotation/center-offset
    math runs in the ``temper-io-types`` kernel.
    """
    # Get discrete rotations (to_discrete returns (positions, rotation_indices))
    _, rotation_indices = state.to_discrete()

    positions = [
        (float(state.positions[i, 0]), float(state.positions[i, 1]))
        for i in range(len(component_refs))
    ]
    rotation_indices_list = [int(rotation_indices[i]) for i in range(len(component_refs))]

    center_offsets = extract_center_offsets(components) if components else {}

    return _rs_state_to_placements(
        positions,
        rotation_indices_list,
        component_refs,
        origin,
        center_offsets or None,
        original_angles or None,
    )


def extract_original_angles(components: list) -> dict[str, float]:
    """
    Extract original angles from component attributes.
    """
    return _rs_extract_original_angles(components)


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
    """
    placements = state_to_placements(state, component_refs, origin, components=components)
    return write_placements_to_pcb(template_pcb, output_pcb, placements)


def validate_output_pcb(output_pcb: Path) -> tuple[bool, list[str]]:
    """
    Validate that the output PCB file is readable.

    This is a kiutils-read validation helper — kept across the boundary (it
    exists to exercise ``KiBoard.from_file`` itself).
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

    The component-position map and the offset rotation run in the
    ``temper-io-types`` ``add_isolation_slots_plan`` kernel; the kiutils
    ``GrLine`` construction stays here.
    """
    warnings: list[str] = []
    slots_added = 0
    slots_skipped = 0

    # Load the PCB
    try:
        ki_board = KiBoard.from_file(str(pcb_path))
    except Exception as e:
        raise ValueError(f"Failed to load PCB: {e}") from e

    # The plan's own count is informational; the authoritative count is the
    # number of GrLine items actually constructed below (matching the pinned
    # Python, which counts construction successes).
    _line_specs, _plan_added, _plan_skipped, _plan_warnings = add_isolation_slots_plan(
        ki_board.footprints, isolation_slots
    )
    warnings.extend(_plan_warnings)
    slots_skipped = _plan_skipped

    # Construct the GrLine items (kiutils boundary; the pinned Python wraps
    # construction in try/except and counts failures as skipped).
    for name, start_x, start_y, end_x, end_y, width_mm in _line_specs:
        try:
            slot_line = GrLine(
                start=Position(X=start_x, Y=start_y),
                end=Position(X=end_x, Y=end_y),
                layer="Edge.Cuts",
                width=width_mm,
            )
            ki_board.graphicItems.append(slot_line)
            slots_added += 1
        except Exception as e:
            warnings.append(f"Failed to add slot '{name}': {e}")
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
    """
    from temper_placer.io.config_loader import IsolationSlot

    specs = _rs_compute_to247_isolation_slots(component_refs, slot_width_mm, slot_length_mm)
    return [
        IsolationSlot(
            name=name,
            component_ref=comp_ref,
            start_offset=start_offset,
            end_offset=end_offset,
            width_mm=width_mm,
            lv_pin=lv_pin,
            hv_pin=hv_pin,
            description=description,
        )
        for name, comp_ref, start_offset, end_offset, width_mm, lv_pin, hv_pin, description in specs
    ]
