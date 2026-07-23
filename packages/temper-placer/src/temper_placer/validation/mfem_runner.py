"""MFEM FEM runner — wraps the compiled serial Poisson example as a subprocess.

U1 of the external-MFEM corroboration plan.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass

import numpy as np


def check_mfem(binary_path: str | None = None) -> bool:
    """Return True if the compiled MFEM custom solver binary is available."""
    path = binary_path or os.environ.get("MFEM_SOLVER_PATH", "/tmp/mfem_tempsolve")
    return os.path.isfile(path)


@dataclass
class MFEMResult:
    """Parsed output from an MFEM serial Poisson solve."""

    node_coords: np.ndarray | None
    """(N, 3) array of node (x, y, z) coordinates in mm, or None."""
    temperature: np.ndarray
    """(N,) array of nodal temperatures in C."""


class MFEMRunner:
    """Run a compiled MFEM serial example binary (subprocess)."""

    def __init__(
        self,
        binary_path: str = "/tmp/mfem_tempsolve",
        timeout_s: int = 300,
    ) -> None:
        self._binary = binary_path
        self._timeout = timeout_s

    def run(self, mesh_path: str, output_dir: str | None = None) -> MFEMResult:
        """Run the MFEM Poisson example on *mesh_path* and parse VTK output."""
        if not os.path.isfile(mesh_path):
            raise FileNotFoundError(f"mesh file not found: {mesh_path}")

        out = output_dir or tempfile.mkdtemp(prefix="mfem_")
        os.makedirs(out, exist_ok=True)
        os.path.splitext(os.path.basename(mesh_path))[0]
        result_path = os.path.join(out, "temperatures.csv")
        cmd = [self._binary, "-m", mesh_path]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                cwd=out,
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"MFEM solve timed out after {self._timeout}s") from e
        if proc.returncode != 0:
            raise RuntimeError(f"MFEM exit code {proc.returncode}: {proc.stderr[:500]}")

        if not os.path.isfile(result_path):
            raise RuntimeError(f"MFEM did not produce CSV output at {result_path}")

        return _parse_csv(result_path)


def _parse_csv(csv_path: str) -> MFEMResult:
    """Parse the temperatures.csv produced by the custom MFEM solver."""
    data = np.loadtxt(csv_path, delimiter=",", skiprows=1, dtype=np.float64)
    if data.ndim == 1:
        data = data.reshape(1, -1)
    node_coords = data[:, :3] if data.shape[1] >= 3 else None
    temperature = data[:, 3] if data.shape[1] >= 4 else data[:, -1]
    return MFEMResult(node_coords=node_coords, temperature=temperature)


# Legacy VTK parser kept for compatibility
def _parse_vtk(vtk_path: str) -> MFEMResult:
    """Parse an MFEM unstructured-grid VTK XML file.

    Deprecated: the custom MFEM solver writes CSV, not VTK.
    Kept for backward compatibility with any existing VTK files.
    """
    import xml.etree.ElementTree as ET

    tree = ET.parse(vtk_path)
    root = tree.getroot()
    piece = root.find(".//Piece")
    if piece is None:
        raise ValueError("VTK: no Piece element found")

    n_points = int(piece.get("NumberOfPoints", "0"))
    n_cells = int(piece.get("NumberOfCells", "0"))
    if n_points == 0:
        raise ValueError("VTK: zero points in mesh")

    points_elem = piece.find("./Points/DataArray")
    node_coords = None
    if points_elem is not None and points_elem.text:
        node_coords = (
            np.fromstring(points_elem.text.strip(), sep=" ").reshape(n_points, 3).astype(np.float64)
        )

    temp_array = None
    for da in piece.findall(".//CellData/DataArray") + piece.findall(".//PointData/DataArray"):
        if da.get("Name", "").lower() in ("temperature", "solution", "t"):
            if da.text:
                temp_array = np.fromstring(da.text.strip(), sep=" ").astype(np.float64)
            break

    if temp_array is None or len(temp_array) == 0:
        if n_cells > 0:
            temp_array = np.zeros(n_cells, dtype=np.float64)
        elif n_points > 0:
            temp_array = np.zeros(n_points, dtype=np.float64)
        else:
            raise ValueError("VTK: no temperature data and zero cells/points")

    if len(temp_array) == n_cells and n_points > 0:
        expanded = np.zeros(n_points, dtype=np.float64)
        cells_elem = piece.find("./Cells")
        if cells_elem is not None:
            for da in cells_elem.findall("DataArray"):
                if da.get("Name", "").lower() == "connectivity" and da.text:
                    conn = np.fromstring(da.text.strip(), sep=" ").astype(np.int64)
                    for ci in range(n_cells):
                        off = ci * 4
                        if off + 3 < len(conn):
                            for j in range(4):
                                expanded[conn[off + j]] = temp_array[ci]
        temp_array = expanded

    return MFEMResult(node_coords=node_coords, temperature=temp_array)
