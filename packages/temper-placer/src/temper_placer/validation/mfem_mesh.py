"""MFEM mesh converter — board model to Gmsh mesh definition.

U2 of the external-MFEM corroboration plan.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np


def build_temper_mesh(
    board: "Board",
    fdm_config: "ThermalFDMConfig",
    device_thermal: dict[str, "DeviceThermalConfig"],
    power_map: dict[str, float] | None = None,
    output_dir: str | None = None,
) -> str:
    """Generate an MFEM-compatible Gmsh mesh definition for the temper board.

    Returns the path to the generated ``.msh`` file.
    """
    out = output_dir or os.path.join(
        os.getcwd(), "mfem_mesh"
    )
    os.makedirs(out, exist_ok=True)
    msh_path = os.path.join(out, "temper_board.msh")

    w = board.width
    h = board.height
    thickness = board.layer_stackup.thickness if board.layer_stackup else 1.6
    power_map = power_map or {}

    lines = [
        "$MeshFormat",
        "4.1 0 8",
        "$EndMeshFormat",
        "$Nodes",
        "8",  # 8 corner nodes of the extruded hex
    ]
    # 8 corners of the 3D board: (x,y,z) — z=0 and z=thickness
    for zi, z in enumerate([0.0, thickness]):
        for yi, y in enumerate([0.0, h]):
            for xi, x in enumerate([0.0, w]):
                nid = zi * 4 + yi * 2 + xi + 1
                lines.append(f"{nid} {x:.6f} {y:.6f} {z:.6f}")
    lines.append("$EndNodes")
    lines.append("$Elements")
    lines.append("1")  # 1 hex element
    # hex element: type 5 (8-node hex), 2 tags (physical=1, elementary=1)
    lines.append("1 5 2 1 1 1 2 3 4 5 6 7 8")
    lines.append("$EndElements")

    Path(msh_path).write_text("\n".join(lines) + "\n")
    return msh_path


def _build_geo(board, fdm_config, power_map):
    """Legacy geo generation (for compatibility)."""
    return build_temper_mesh(board, fdm_config, {}, power_map)
