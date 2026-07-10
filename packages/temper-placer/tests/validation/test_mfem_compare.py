"""Tests for MFEM comparison instrument (U3)."""

from __future__ import annotations

import numpy as np

from temper_placer.validation.mfem_compare import (
    ComparisonResult,
    compare_fields,
    project_mfem_to_fdm,
)


class MockMFEMResult:
    def __init__(self, temperature, node_coords=None):
        self.temperature = np.asarray(temperature, dtype=np.float64)
        self.node_coords = (
            np.asarray(node_coords, dtype=np.float64) if node_coords is not None else None
        )


class MockFDMConfig:
    cell_size_mm = 1.0
    origin_mm = (0.0, 0.0)
    height_cells = 10
    width_cells = 10


def test_identical_fields_clean():
    """Two identical fields produce zero delta and no tolerance violation."""
    fdm = np.full((10, 10), 100.0, dtype=np.float64)
    mfem = fdm.copy()
    result = compare_fields(fdm, mfem, tolerance_C=5.0)
    assert not result.exceeds_tolerance
    assert result.max_delta_C == 0.0
    assert "agree" in result.attribution


def test_device_hotspot_violation():
    """A hotspot at a device location is attributed to that device."""
    fdm = np.full((10, 10), 100.0, dtype=np.float64)
    mfem = fdm.copy()
    mfem[5, 3] = 120.0  # hotspot at (row=5, col=3)
    result = compare_fields(
        fdm, mfem, tolerance_C=5.0,
        devices={"Q1": (5, 3)},
    )
    assert result.exceeds_tolerance
    assert result.max_delta_C == 20.0
    assert result.device_deltas["Q1"] == 20.0


def test_far_field_attribution():
    """Disagreement far from the heatsink edge gets far-field attribution."""
    fdm = np.full((10, 10), 100.0, dtype=np.float64)
    mfem = fdm.copy()
    mfem[4, 5] = 115.0  # far from TOP/BOTTOM edges
    result = compare_fields(
        fdm, mfem, tolerance_C=5.0, heatsink_edge="TOP",
    )
    assert result.exceeds_tolerance
    assert "far-field" in result.attribution


def test_shape_mismatch_raises():
    """compare_fields raises on mismatched field shapes."""
    fdm = np.full((10, 10), 100.0)
    mfem = np.full((8, 8), 100.0)
    try:
        compare_fields(fdm, mfem)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_project_mfem_to_fdm_reshape():
    """project_mfem_to_fdm falls back to reshape when node coords are absent."""
    result = MockMFEMResult(np.arange(100, dtype=np.float64).reshape(-1))
    config = MockFDMConfig()
    projected = project_mfem_to_fdm(result, config)
    assert projected.shape == (10, 10)
    assert projected[0, 0] == 0.0
    assert projected[9, 9] == 99.0
