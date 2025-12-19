"""
Placement exporter for DRC validation.

This module provides bridge functions to export current optimization state
to temporary PCB files for DRC validation. It handles:
- Soft rotation to discrete conversion (argmax of one-hot)
- Component reference ordering from LossContext
- Board origin offset application
- Temporary file management

Example usage:
    >>> from temper_placer.io.placement_exporter import create_pcb_exporter
    >>>
    >>> # Create exporter for DRCLoss
    >>> exporter = create_pcb_exporter(
    ...     template_pcb=Path("/path/to/template.kicad_pcb"),
    ...     board_origin=(100.0, 50.0),  # mm
    ... )
    >>>
    >>> # Use with DRCLoss
    >>> drc_loss = DRCLoss(
    ...     validator=KiCadDRCValidator(),
    ...     pcb_exporter=exporter,
    ... )
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path

import jax.numpy as jnp
from jax import Array

from temper_placer.io.kicad_writer import PlacementUpdate, write_placements_to_pcb
from temper_placer.losses.types import LossContext


def soft_to_discrete_rotations(rotations: Array) -> Array:
    """
    Convert soft one-hot rotations to discrete rotation indices.

    During training, rotations are (N, 4) soft one-hot vectors from
    Gumbel-Softmax. For DRC, we need discrete rotations (0, 1, 2, 3)
    representing 0°, 90°, 180°, 270°.

    Args:
        rotations: (N, 4) soft one-hot rotation vectors.

    Returns:
        (N,) array of rotation indices (0-3).
    """
    return jnp.argmax(rotations, axis=-1)


def rotation_index_to_degrees(index: int) -> float:
    """Convert rotation index (0-3) to degrees (0, 90, 180, 270)."""
    return float(index) * 90.0


def positions_to_placements(
    positions: Array,
    rotations: Array,
    component_refs: list[str],
    origin: tuple[float, float] = (0.0, 0.0),
) -> dict[str, PlacementUpdate]:
    """
    Convert position/rotation arrays to PlacementUpdate dictionary.

    This is the core conversion function that bridges the optimization state
    (JAX arrays) to KiCad format (named components with absolute positions).

    Args:
        positions: (N, 2) array of component center positions in mm.
        rotations: (N, 4) soft one-hot rotation vectors.
        component_refs: List of N component reference designators, in order.
        origin: (x, y) board origin offset to add to positions.

    Returns:
        Dictionary mapping component ref to PlacementUpdate.

    Raises:
        ValueError: If positions/rotations shape doesn't match component_refs length.
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

    placements: dict[str, PlacementUpdate] = {}

    for i, ref in enumerate(component_refs):
        # Get position (add origin offset)
        x = float(positions[i, 0]) + origin[0]
        y = float(positions[i, 1]) + origin[1]

        # Convert rotation index to degrees
        rot_idx = int(rotation_indices[i])
        rotation_deg = rotation_index_to_degrees(rot_idx)

        placements[ref] = PlacementUpdate(
            ref=ref,
            x=x,
            y=y,
            rotation=rotation_deg,
        )

    return placements


def export_positions_to_temp_pcb(
    positions: Array,
    rotations: Array,
    context: LossContext,
    template_pcb: Path,
    board_origin: tuple[float, float] = (0.0, 0.0),
    temp_dir: Path | None = None,
) -> Path:
    """
    Export current placement state to a temporary PCB file for DRC.

    This function:
    1. Converts soft rotations to discrete (argmax)
    2. Extracts component refs from context.netlist in order
    3. Applies board origin offset to positions
    4. Writes placement updates to a temp copy of the template PCB

    The caller is responsible for cleaning up the temp file.

    Args:
        positions: (N, 2) array of component positions in mm.
        rotations: (N, 4) soft one-hot rotation vectors.
        context: LossContext containing netlist with component order.
        template_pcb: Path to the template .kicad_pcb file.
        board_origin: (x, y) offset to add to all positions.
        temp_dir: Directory for temp files (uses system temp if None).

    Returns:
        Path to the temporary PCB file.

    Raises:
        ValueError: If template doesn't exist or positions don't match netlist.
        RuntimeError: If PCB write fails.
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
        )

        if result.has_warnings:
            # Log warnings but don't fail
            # In production, might want to use proper logging
            pass

        return temp_path

    except Exception as e:
        # Clean up temp file on failure
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass
        raise RuntimeError(f"Failed to write temp PCB: {e}") from e


# Type alias for the exporter function signature expected by DRCLoss
PCBExporterFn = Callable[[Array, Array, LossContext], Path]


def create_pcb_exporter(
    template_pcb: Path,
    board_origin: tuple[float, float] = (0.0, 0.0),
    temp_dir: Path | None = None,
) -> PCBExporterFn:
    """
    Factory function to create a PCB exporter for DRCLoss.

    This returns a function with the signature expected by DRCLoss:
        (positions, rotations, context) -> Path

    The template_pcb and board_origin are captured in the closure.

    Args:
        template_pcb: Path to the template .kicad_pcb file.
        board_origin: (x, y) offset to add to all positions.
        temp_dir: Directory for temp files (uses system temp if None).

    Returns:
        PCB exporter function suitable for DRCLoss.pcb_exporter parameter.

    Example:
        >>> exporter = create_pcb_exporter(
        ...     template_pcb=Path("board.kicad_pcb"),
        ...     board_origin=(100.0, 50.0),
        ... )
        >>> drc_loss = DRCLoss(pcb_exporter=exporter)
    """

    def exporter(positions: Array, rotations: Array, context: LossContext) -> Path:
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

    Args:
        path: Path to the temp PCB file.

    Returns:
        True if deleted, False if file didn't exist or couldn't be deleted.
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
