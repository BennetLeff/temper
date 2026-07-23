"""Tests for MFEM runner (U1)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

from temper_placer.validation.mfem_runner import (
    MFEMResult,
    MFEMRunner,
    _parse_csv,
    check_mfem,
)

_MFEM_BINARY = "/tmp/mfem_tempsolve"
_MFEM_DATA = "/tmp/mfem-build/data"


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------


def test_check_mfem_binary_present():
    """check_mfem returns True when the compiled binary exists."""
    assert check_mfem(_MFEM_BINARY), f"MFEM binary not found at {_MFEM_BINARY}"


def test_check_mfem_binary_absent():
    """check_mfem returns False when the binary doesn't exist."""
    assert not check_mfem("/nonexistent/path/ex1")


# ---------------------------------------------------------------------------
# Runner — integration (requires MFEM binary + star.mesh)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not Path(_MFEM_BINARY).is_file(),
    reason="MFEM binary not compiled",
)
def test_runner_star_mesh():
    """MFEMRunner.run() on star.mesh produces a valid CSV result."""
    mesh = f"{_MFEM_DATA}/star.mesh"
    if not Path(mesh).is_file():
        pytest.skip("star.mesh not found")
    runner = MFEMRunner(binary_path=_MFEM_BINARY)
    with tempfile.TemporaryDirectory() as tmp:
        result = runner.run(mesh, output_dir=tmp)
        assert isinstance(result, MFEMResult)
        assert result.temperature is not None
        assert len(result.temperature) > 0
        assert np.isfinite(result.temperature).all()


@pytest.mark.skipif(
    not Path(_MFEM_BINARY).is_file(),
    reason="MFEM binary not compiled",
)
def test_runner_missing_mesh_raises():
    """MFEMRunner.run() raises FileNotFoundError for a nonexistent mesh."""
    runner = MFEMRunner(binary_path=_MFEM_BINARY)
    with pytest.raises(FileNotFoundError):
        runner.run("/nonexistent/mesh.msh")


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------


def test_parse_csv_synthetic():
    """_parse_csv on a minimal valid CSV returns the correct temperature."""
    csv_content = "x,y,z,temperature\n0.0,0.0,0.0,100.0\n1.0,0.0,0.0,200.0\n"
    path = Path(tempfile.gettempdir()) / "_test_mfem_synthetic.csv"
    path.write_text(csv_content)
    result = _parse_csv(str(path))
    assert len(result.temperature) == 2
    assert result.temperature[0] == 100.0
    assert result.temperature[1] == 200.0
    path.unlink()
