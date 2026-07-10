"""
Tests for Elmer orchestrator (validation/elmer.py).

Covers:
- ``check_elmer()`` preflight: returns False when Elmer absent.
- ``ElmerRunner.run()``: error path when ElmerSolver not found, timeout
  handling, VTU parsing (synthetic/canned VTU file).
- Happy-path VTU parse using a minimal valid VTU XML string.

Elmer is NOT installed — tests that need the real CLI skip gracefully.
"""

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from temper_placer.validation.elmer import (
    ElmerResult,
    ElmerRunner,
    check_elmer,
)


# ---------------------------------------------------------------------------
# Minimal valid VTU XML for parse testing
# ---------------------------------------------------------------------------

def _make_vtu_xml(temperatures: list[float]) -> str:
    """Build a minimal valid VTU XML containing a temperature DataArray."""
    n = len(temperatures)
    coords = " ".join("0 0 0" for _ in range(n))
    temp_str = " ".join(f"{t:.6f}" for t in temperatures)
    return f"""<?xml version="1.0"?>
<VTKFile type="UnstructuredGrid" version="0.1" byte_order="LittleEndian">
  <UnstructuredGrid>
    <Piece NumberOfPoints="{n}" NumberOfCells="0">
      <Points>
        <DataArray type="Float64" Name="Points" NumberOfComponents="3" format="ascii">
          {coords}
        </DataArray>
      </Points>
      <PointData>
        <DataArray type="Float64" Name="temperature" format="ascii">
          {temp_str}
        </DataArray>
      </PointData>
      <Cells>
        <DataArray type="Int32" Name="connectivity" format="ascii"/>
        <DataArray type="Int32" Name="offsets" format="ascii"/>
        <DataArray type="UInt8" Name="types" format="ascii"/>
      </Cells>
    </Piece>
  </UnstructuredGrid>
</VTKFile>
"""


# ---------------------------------------------------------------------------
# Preflight tests
# ---------------------------------------------------------------------------


class TestCheckElmer:
    """Preflight: ``check_elmer()`` detects Elmer CLI availability."""

    def test_elmer_absent(self):
        """Preflight returns False when Elmer is not installed."""
        # Elmer CANNOT be installed (critical context) — always False here
        assert check_elmer() is False

    def test_elmer_present_when_on_path(self, monkeypatch):
        """Preflight returns True when both tools are on PATH."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            fake_grid = Path(td) / "ElmerGrid"
            fake_solver = Path(td) / "ElmerSolver"
            fake_grid.touch(mode=0o755)
            fake_solver.touch(mode=0o755)

            original_path = shutil.which("ElmerGrid")
            monkeypatch.setattr(
                shutil, "which",
                lambda name: str(fake_grid) if name == "ElmerGrid"
                else (str(fake_solver) if name == "ElmerSolver"
                      else None)
            )
            assert check_elmer() is True

    def test_elmer_partial_missing_grid(self, monkeypatch):
        """Preflight returns False when only ElmerSolver is on PATH."""
        monkeypatch.setattr(
            shutil, "which",
            lambda name: "/usr/bin/ElmerSolver" if name == "ElmerSolver"
            else None
        )
        assert check_elmer() is False

    def test_elmer_partial_missing_solver(self, monkeypatch):
        """Preflight returns False when only ElmerGrid is on PATH."""
        monkeypatch.setattr(
            shutil, "which",
            lambda name: "/usr/bin/ElmerGrid" if name == "ElmerGrid"
            else None
        )
        assert check_elmer() is False


# ---------------------------------------------------------------------------
# ElmerResult tests
# ---------------------------------------------------------------------------


class TestElmerResult:
    """ElmerResult dataclass behaviour."""

    def test_success_result(self):
        T = np.array([20.0, 25.0, 30.0], dtype=np.float64)
        r = ElmerResult(success=True, temperature_field=T, elapsed_ms=123.4)
        assert r.success
        assert np.array_equal(r.temperature_field, T)  # type: ignore[arg-type]
        assert r.elapsed_ms == 123.4
        assert r.error_message == ""

    def test_failure_result(self):
        r = ElmerResult(success=False, error_message="timeout")
        assert not r.success
        assert r.temperature_field is None
        assert "timeout" in r.error_message

    def test_empty_success(self):
        r = ElmerResult(success=True)
        assert r.success
        assert r.temperature_field is None


# ---------------------------------------------------------------------------
# ElmerRunner availability
# ---------------------------------------------------------------------------


class TestElmerRunnerAvailability:
    """ElmerRunner.is_available mirrors check_elmer()."""

    def test_is_available_false_when_missing(self):
        runner = ElmerRunner()
        # Elmer not installed — is_available should be False
        assert runner.is_available is False

    def test_is_available_true_when_on_path(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
        runner = ElmerRunner()
        assert runner.is_available is True


# ---------------------------------------------------------------------------
# ElmerRunner.run() — error paths (Elmer absent)
# ---------------------------------------------------------------------------


class TestElmerRunnerErrorPaths:
    """Error paths: missing CLI, missing mesh dir, missing sif."""

    def test_run_when_elmer_not_available(self, tmp_path):
        """Runner returns failure when ElmerSolver is not on PATH."""
        runner = ElmerRunner()
        assert not runner.is_available

        result = runner.run(
            mesh_dir=tmp_path,
            sif_path=tmp_path / "case.sif",
        )
        assert not result.success
        assert "not available" in result.error_message.lower()

    def test_run_missing_mesh_dir(self, tmp_path, monkeypatch):
        """Runner returns failure when mesh directory doesn't exist."""
        monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
        runner = ElmerRunner()

        fake_mesh = tmp_path / "nonexistent_mesh"
        result = runner.run(
            mesh_dir=fake_mesh,
            sif_path=tmp_path / "case.sif",
        )
        assert not result.success
        assert "does not exist" in result.error_message

    def test_run_missing_sif(self, tmp_path, monkeypatch):
        """Runner returns failure when .sif file doesn't exist."""
        monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
        runner = ElmerRunner()

        mesh_dir = tmp_path / "mesh"
        mesh_dir.mkdir()
        fake_sif = tmp_path / "missing.sif"

        result = runner.run(mesh_dir=mesh_dir, sif_path=fake_sif)
        assert not result.success
        assert "does not exist" in result.error_message


# ---------------------------------------------------------------------------
# VTU parsing (synthetic/canned — no Elmer needed)
# ---------------------------------------------------------------------------


class TestVTUParsing:
    """VTU parse logic using synthetic XML strings."""

    def test_parse_valid_vtu(self, tmp_path):
        """Parse a minimal valid VTU with a temperature DataArray."""
        temps = [40.0, 42.5, 41.0, 43.0, 40.5]
        vtu_xml = _make_vtu_xml(temps)
        vtu_path = tmp_path / "results.vtu"
        vtu_path.write_text(vtu_xml)

        result = ElmerRunner._parse_vtu(vtu_path, 100.0)
        assert result.success
        assert result.temperature_field is not None
        np.testing.assert_array_almost_equal(
            result.temperature_field, np.array(temps, dtype=np.float64)
        )

    def test_parse_vtu_missing_file(self, tmp_path):
        """Parse fails on a non-existent file."""
        result = ElmerRunner._parse_vtu(tmp_path / "missing.vtu", 0.0)
        assert not result.success
        assert "error" in result.error_message.lower()

    def test_parse_vtu_no_temperature(self, tmp_path):
        """Parse fails when VTU contains no temperature DataArray."""
        vtu_xml = """<?xml version="1.0"?>
<VTKFile type="UnstructuredGrid" version="0.1">
  <UnstructuredGrid>
    <Piece NumberOfPoints="2" NumberOfCells="0">
      <Points>
        <DataArray type="Float64" Name="Points" NumberOfComponents="3" format="ascii">
          0 0 0 1 1 1
        </DataArray>
      </Points>
      <PointData>
        <DataArray type="Float64" Name="pressure" format="ascii">
          1.0 2.0
        </DataArray>
      </PointData>
      <Cells>
        <DataArray type="Int32" Name="connectivity" format="ascii"/>
        <DataArray type="Int32" Name="offsets" format="ascii"/>
        <DataArray type="UInt8" Name="types" format="ascii"/>
      </Cells>
    </Piece>
  </UnstructuredGrid>
</VTKFile>
"""
        vtu_path = tmp_path / "no_temp.vtu"
        vtu_path.write_text(vtu_xml)

        result = ElmerRunner._parse_vtu(vtu_path, 0.0)
        assert not result.success
        assert "no temperature" in result.error_message.lower()

    def test_parse_vtu_with_scalars_attribute(self, tmp_path):
        """Parse a VTU where temperature is the Scalars attribute on PointData."""
        temps = [50.0, 52.0, 51.0]
        temp_str = " ".join(f"{t:.6f}" for t in temps)
        vtu_xml = f"""<?xml version="1.0"?>
<VTKFile type="UnstructuredGrid" version="0.1">
  <UnstructuredGrid>
    <Piece NumberOfPoints="3" NumberOfCells="0">
      <Points>
        <DataArray type="Float64" Name="Points" NumberOfComponents="3" format="ascii">
          0 0 0 1 1 1 2 2 2
        </DataArray>
      </Points>
      <PointData Scalars="temperature">
        <DataArray type="Float64" Name="temperature" format="ascii">
          {temp_str}
        </DataArray>
      </PointData>
      <Cells>
        <DataArray type="Int32" Name="connectivity" format="ascii"/>
        <DataArray type="Int32" Name="offsets" format="ascii"/>
        <DataArray type="UInt8" Name="types" format="ascii"/>
      </Cells>
    </Piece>
  </UnstructuredGrid>
</VTKFile>
"""
        vtu_path = tmp_path / "scalars.vtu"
        vtu_path.write_text(vtu_xml)

        result = ElmerRunner._parse_vtu(vtu_path, 0.0)
        assert result.success
        assert result.temperature_field is not None
        np.testing.assert_array_almost_equal(
            result.temperature_field, np.array(temps, dtype=np.float64)
        )

    def test_timeout_error_path(self, tmp_path, monkeypatch):
        """Runner catches subprocess TimeoutExpired."""
        import subprocess as sp_mod

        monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
        mesh_dir = tmp_path / "mesh"
        mesh_dir.mkdir()
        sif_path = tmp_path / "case.sif"
        sif_path.write_text("! dummy sif\n")

        # Patch subprocess.run to raise TimeoutExpired
        def _raise_timeout(*args, **kwargs):
            raise sp_mod.TimeoutExpired(cmd=["ElmerSolver"], timeout=1.0)

        with patch("subprocess.run", _raise_timeout):
            runner = ElmerRunner(timeout_s=1.0)
            result = runner.run(
                mesh_dir=mesh_dir,
                sif_path=sif_path,
            )
            assert not result.success
            assert "timed out" in result.error_message.lower()

    def test_csv_parse(self, tmp_path):
        """CSV fallback parsing extracts the temperature column."""
        csv_content = "Node,temperature,pressure\n0,40.0,1.0\n1,42.5,1.0\n2,41.0,1.0\n"
        csv_path = tmp_path / "results.csv"
        csv_path.write_text(csv_content)

        result = ElmerRunner._parse_csv(csv_path, 0.0)
        assert result.success
        assert result.temperature_field is not None
        np.testing.assert_array_almost_equal(
            result.temperature_field, np.array([40.0, 42.5, 41.0], dtype=np.float64)
        )

    def test_csv_parse_empty(self, tmp_path):
        """CSV parsing fails on empty file."""
        csv_path = tmp_path / "empty.csv"
        csv_path.write_text("")

        result = ElmerRunner._parse_csv(csv_path, 0.0)
        assert not result.success
