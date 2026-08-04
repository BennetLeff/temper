"""
Placement exporter for DRC validation.

Wave 4, Phase 3, candidate 4: the position/rotation conversion kernels
(``positions_to_placements``, ``rotation_index_to_degrees``) delegate to
``temper-io-types``; ``np.argmax`` (``soft_to_discrete_rotations``) stays
here per the phase plan's no-numpy-interop boundary, and the temp-file
orchestration is unchanged.
"""

from __future__ import annotations

import contextlib
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeAlias

import numpy as np
from numpy.typing import NDArray

Array: TypeAlias = NDArray

from temper_io_types import (
    positions_to_placements as _rs_positions_to_placements,
)
from temper_io_types import (
    rotation_index_to_degrees as _rs_rotation_index_to_degrees,
)

from temper_placer.io.kicad_writer import PlacementUpdate, write_placements_to_pcb


def soft_to_discrete_rotations(rotations: Array) -> Array:
    """
    Convert soft one-hot rotations to discrete rotation indices.

    ``np.argmax`` is kept across the boundary (the phase plan declines to
    assume a numpy-interop dependency; see the DSN candidate's boundary note).
    """
    return np.argmax(rotations, axis=-1)


def rotation_index_to_degrees(index: int) -> float:
    """Convert rotation index (0-3) to degrees (0, 90, 180, 270)."""
    return _rs_rotation_index_to_degrees(int(index))


def positions_to_placements(
    positions: Array,
    rotations: Array,
    component_refs: list[str],
    origin: tuple[float, float] = (0.0, 0.0),
) -> dict[str, PlacementUpdate]:
    """
    Convert position/rotation arrays to PlacementUpdate dictionary.

    The shape guards and the numpy extraction stay here; the per-component
    math runs in the ``temper-io-types`` kernel.
    """
    n_components = len(component_refs)

    if positions.shape[0] != n_components:
        raise ValueError(
            f"Position count ({positions.shape[0]}) doesn't match component count ({n_components})"
        )

    if rotations.shape[0] != n_components:
        raise ValueError(
            f"Rotation count ({rotations.shape[0]}) doesn't match component count ({n_components})"
        )

    # Convert soft rotations to discrete indices
    rotation_indices = soft_to_discrete_rotations(rotations)

    positions_list = [
        (float(positions[i, 0]), float(positions[i, 1])) for i in range(n_components)
    ]
    rotation_indices_list = [int(rotation_indices[i]) for i in range(n_components)]

    return _rs_positions_to_placements(positions_list, rotation_indices_list, component_refs, origin)


def export_positions_to_temp_pcb(
    positions: Array,
    rotations: Array,
    context: Any,
    template_pcb: Path,
    board_origin: tuple[float, float] = (0.0, 0.0),
    temp_dir: Path | None = None,
) -> Path:
    """
    Export current placement state to a temporary PCB file for DRC.
    """
    if not template_pcb.exists():
        raise ValueError(f"Template PCB not found: {template_pcb}")

    # Get component refs in array order from netlist
    component_refs = [comp.ref for comp in context.netlist.components]

    # Convert to placement updates
    placements = positions_to_placements(
        positions=positions,
        rotations=rotations,
        component_refs=component_refs,
        origin=board_origin,
    )

    # Create temp file
    if temp_dir is not None:
        temp_dir.mkdir(parents=True, exist_ok=True)
        fd, temp_path_str = tempfile.mkstemp(
            suffix=".kicad_pcb",
            prefix="temper_drc_",
            dir=str(temp_dir),
        )
    else:
        fd, temp_path_str = tempfile.mkstemp(
            suffix=".kicad_pcb",
            prefix="temper_drc_",
        )

    # Close the file descriptor (we'll write via kiutils)
    import os

    os.close(fd)

    temp_path = Path(temp_path_str)

    try:
        result = write_placements_to_pcb(
            template_pcb=template_pcb,
            output_pcb=temp_path,
            placements=placements,
            preserve_unmatched=True,
            components=context.netlist.components,  # For center offset conversion
        )

        if result.has_warnings:
            # Log warnings but don't fail
            # In production, might want to use proper logging
            pass

        return temp_path

    except Exception as e:
        # Clean up temp file on failure
        if temp_path.exists():
            with contextlib.suppress(Exception):
                temp_path.unlink()
        raise RuntimeError(f"Failed to write temp PCB: {e}") from e


PCBExporterFn = Callable[[Array, Array, Any], Path]


def create_pcb_exporter(
    template_pcb: Path,
    board_origin: tuple[float, float] = (0.0, 0.0),
    temp_dir: Path | None = None,
) -> PCBExporterFn:
    """
    Factory function to create a PCB exporter for DRC validation.
    """

    def exporter(positions: Array, rotations: Array, context: Any) -> Path:
        return export_positions_to_temp_pcb(
            positions=positions,
            rotations=rotations,
            context=context,
            template_pcb=template_pcb,
            board_origin=board_origin,
            temp_dir=temp_dir,
        )

    return exporter


def cleanup_temp_pcb(path: Path) -> bool:
    """
    Safely delete a temporary PCB file.
    """
    if not path.exists():
        return False

    try:
        path.unlink()
        return True
    except Exception:
        return False


__all__ = [
    "soft_to_discrete_rotations",
    "rotation_index_to_degrees",
    "positions_to_placements",
    "export_positions_to_temp_pcb",
    "create_pcb_exporter",
    "cleanup_temp_pcb",
    "PCBExporterFn",
]
