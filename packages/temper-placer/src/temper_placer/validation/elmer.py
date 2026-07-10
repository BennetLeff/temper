"""
Elmer FEM orchestrator — wraps ElmerSolver CLI for external thermal corroboration.

Mirrors the ``validation/spice.py`` ``NgspiceValidator`` pattern for preflight
check and subprocess invocation.  Deterministic: same inputs → same output.

When Elmer is not installed, :func:`check_elmer` returns ``False`` so the gate
can return ``UNMEASURED`` (fail-closed, never a silent pass).

Requirements: R1 (Python orchestrator), R5 (same-objective discipline).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import numpy as np


def check_elmer() -> bool:
    """Preflight: are ``ElmerGrid`` and ``ElmerSolver`` on PATH?

    Returns ``True`` when both CLI tools are discoverable via ``shutil.which``.
    A missing binary means the external FEM corroboration instrument is absent
    — the gate returns ``UNMEASURED`` (fail-closed).

    Note:
        This is a simple PATH check, not a functional probe.
        ``ElmerRunner`` handles timeout / exit-code / parse errors at solve time.
    """
    return shutil.which("ElmerGrid") is not None and shutil.which("ElmerSolver") is not None


@dataclass(frozen=True)
class ElmerResult:
    """Result from an ElmerSolver run.

    Attributes:
        success: Whether the solve completed without errors.
        temperature_field: Parsed temperature field (numpy array) or ``None``.
        elapsed_ms: Wall-clock solve time in milliseconds.
        error_message: Error description when ``success`` is ``False``.
    """

    success: bool
    temperature_field: np.ndarray | None = None
    elapsed_ms: float = 0.0
    error_message: str = ""


class ElmerRunner:
    """Wrapper around the ElmerSolver CLI for steady-state thermal simulation.

    Example usage::

        runner = ElmerRunner(timeout_s=300)
        result = runner.run(mesh_dir=Path("mesh"), sif_path=Path("case.sif"))
        if result.success:
            T_field = result.temperature_field  # numpy array
    """

    def __init__(self, timeout_s: float = 300.0):
        self._timeout_s = timeout_s
        self._elmer_solver = shutil.which("ElmerSolver")

    @property
    def is_available(self) -> bool:
        """Return ``True`` when ElmerSolver is on PATH."""
        return self._elmer_solver is not None

    def run(
        self,
        mesh_dir: Path,
        sif_path: Path,
    ) -> ElmerResult:
        """Run ElmerSolver in *mesh_dir* with the given solver-input file.

        Args:
            mesh_dir: Directory containing the Elmer mesh files.
            sif_path: Path to the ``.sif`` solver-input file.

        Returns:
            ``ElmerResult`` with the parsed temperature field on success,
            or an error message on failure / timeout / parse error.
        """
        t_start = time.monotonic()

        if not self.is_available:
            return ElmerResult(
                success=False,
                elapsed_ms=(time.monotonic() - t_start) * 1000.0,
                error_message="ElmerSolver not available on PATH",
            )

        if not mesh_dir.is_dir():
            return ElmerResult(
                success=False,
                elapsed_ms=(time.monotonic() - t_start) * 1000.0,
                error_message=f"mesh directory does not exist: {mesh_dir}",
            )

        if not sif_path.is_file():
            return ElmerResult(
                success=False,
                elapsed_ms=(time.monotonic() - t_start) * 1000.0,
                error_message=f"sif file does not exist: {sif_path}",
            )

        # ElmerSolver reads case.sif from its working directory by default
        # We copy the sif to the mesh dir as case.sif and run there
        work_dir = mesh_dir
        dest_sif = work_dir / "case.sif"
        copy_back = dest_sif != sif_path.resolve()

        try:
            if copy_back:
                shutil.copy2(sif_path, dest_sif)

            assert self._elmer_solver is not None
            cmd = [self._elmer_solver]
            env = os.environ.copy()

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self._timeout_s,
                cwd=work_dir,
                env=env,
            )

            elapsed_ms = (time.monotonic() - t_start) * 1000.0

            if proc.returncode != 0:
                joined = proc.stderr + proc.stdout
                hint = joined[-500:] if len(joined) > 500 else joined
                return ElmerResult(
                    success=False,
                    elapsed_ms=elapsed_ms,
                    error_message=(
                        f"ElmerSolver exit code {proc.returncode}: {hint}"
                    ),
                )

            # Parse VTU output
            vtu_files = sorted(work_dir.glob("*.vtu"))
            if not vtu_files:
                csv_files = sorted(work_dir.glob("*.csv"))
                if csv_files:
                    return self._parse_csv(csv_files[0], elapsed_ms)
                return ElmerResult(
                    success=False,
                    elapsed_ms=elapsed_ms,
                    error_message="ElmerSolver produced no VTU or CSV output",
                )

            return self._parse_vtu(vtu_files[-1], elapsed_ms)

        except subprocess.TimeoutExpired:
            return ElmerResult(
                success=False,
                elapsed_ms=(time.monotonic() - t_start) * 1000.0,
                error_message=f"ElmerSolver timed out after {self._timeout_s}s",
            )
        except Exception as exc:
            return ElmerResult(
                success=False,
                elapsed_ms=(time.monotonic() - t_start) * 1000.0,
                error_message=f"ElmerSolver error: {exc}",
            )
        finally:
            if copy_back and dest_sif.exists():
                with __import__("contextlib").suppress(OSError):
                    dest_sif.unlink()

    # ------------------------------------------------------------------
    # VTU parsing — extract scalar temperature field from XML VTU file
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_vtu(vtu_path: Path, elapsed_ms: float) -> ElmerResult:
        """Parse an Elmer VTU (XML unstructured grid) into a numpy array.

        Extracts the ``temperature`` scalar field from the ``PointData``
        section, which is the canonical output variable for Elmer's
        ``HeatSolver``.

        Returns:
            ``ElmerResult`` with ``temperature_field`` as a ``(N,)`` float64
            array of per-node temperatures, or error on parse failure.
        """
        try:
            tree = ET.parse(str(vtu_path))
            root = tree.getroot()

            # Extract point data — Elmer stores temperature in
            # <PointData Scalars="temperature"> or within a <DataArray>
            temp = None
            for elem in root.iter():
                tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                # Elmer classic VTU: <DataArray type="Float64" Name="temperature" ...>
                if tag == "DataArray" and elem.get("Name", "").lower() == "temperature":
                    text = "".join(elem.itertext())
                    vals = np.fromstring(text, sep=" ", dtype=np.float64)
                    temp = vals
                    break

            if temp is None:
                # Try alternate: look for Scalars attribute on PointData
                for pd_elem in root.iter():
                    tag = pd_elem.tag.split("}")[-1] if "}" in pd_elem.tag else pd_elem.tag
                    if tag == "PointData":
                        scalar_name = pd_elem.get("Scalars", "")
                        for child in pd_elem:
                            child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                            if child_tag == "DataArray" and child.get("Name", "") == scalar_name:
                                text = "".join(child.itertext())
                                temp = np.fromstring(text, sep=" ", dtype=np.float64)
                                break

            if temp is None:
                return ElmerResult(
                    success=False,
                    elapsed_ms=elapsed_ms,
                    error_message="VTU file contains no temperature DataArray",
                )

            return ElmerResult(
                success=True,
                temperature_field=temp,
                elapsed_ms=elapsed_ms,
            )

        except Exception as exc:
            return ElmerResult(
                success=False,
                elapsed_ms=elapsed_ms,
                error_message=f"VTU parse error: {exc}",
            )

    # ------------------------------------------------------------------
    # CSV parsing — fallback for Elmer CSV output (SaveData + SaveScalars)
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_csv(csv_path: Path, elapsed_ms: float) -> ElmerResult:
        """Parse an Elmer CSV output file into a numpy array.

        Assumes the CSV has a header row with a ``temperature`` column.
        """
        try:
            import csv as csv_mod

            with open(csv_path, newline="") as f:
                reader = csv_mod.DictReader(f)
                rows = list(reader)

            if not rows:
                return ElmerResult(
                    success=False,
                    elapsed_ms=elapsed_ms,
                    error_message="CSV output is empty",
                )

            # Find temperature column (case-insensitive)
            headers = [h.lower() for h in reader.fieldnames or []]
            t_col = None
            for candidate in ("temperature", "temp", "t"):
                if candidate in headers:
                    t_col = rows[0][reader.fieldnames[headers.index(candidate)]]
                    break

            if t_col is None:
                # Use last column as fallback
                t_col = rows[0][reader.fieldnames[-1]]

            temp = np.array([float(r.get(reader.fieldnames[headers.index(
                next(h for h in headers if h in ("temperature", "temp", "t"))
            )] if any(h in headers for h in ("temperature", "temp", "t")) else reader.fieldnames[-1])) for r in rows], dtype=np.float64)

            return ElmerResult(
                success=True,
                temperature_field=temp,
                elapsed_ms=elapsed_ms,
            )

        except Exception as exc:
            return ElmerResult(
                success=False,
                elapsed_ms=elapsed_ms,
                error_message=f"CSV parse error: {exc}",
            )
