"""
Tests for full-field comparison instrument (validation/elmer_compare.py).

Covers:
- Two identical fields -> zero Delta-T, CLEAN.
- Two fields with a device-region hotspot -> VIOLATIONS with device attribution.
- Far-field-only disagreement -> VIOLATIONS with far-field attribution.
- Field shape mismatch -> error result.
- Per-device T_j spot-checks from area-averaged deltas.

Uses synthetic numpy fields -- no real Elmer output needed.
"""

import numpy as np
import pytest

from temper_placer.physics.thermal_fdm import ThermalFDMConfig
from temper_placer.validation.elmer_compare import (
    AttributionRegion,
    ComparisonResult,
    compare_fields,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _fdm_config(
    H=20, W=30, cell_size=0.5, origin=(0.0, 0.0), hs="TOP"
) -> ThermalFDMConfig:
    return ThermalFDMConfig(
        cell_size_mm=cell_size,
        origin_mm=origin,
        height_cells=H,
        width_cells=W,
        ambient_C=40.0,
        heatsink_edge=hs,
    )


# ---------------------------------------------------------------------------
# Identical fields -> CLEAN
# ---------------------------------------------------------------------------


class TestIdenticalFields:
    """Two identical temperature fields produce zero Delta-T."""

    def test_identical_fields_clean(self):
        cfg = _fdm_config()
        T = np.full((cfg.height_cells, cfg.width_cells), 45.0, dtype=np.float64)
        T[5:8, 5:8] = 80.0  # device hotspot

        result = compare_fields(
            fdm_field=T,
            elmer_field=T.copy(),
            fdm_config=cfg,
            tolerance_C=5.0,
        )
        assert result.is_clean
        assert result.delta_map is not None
        assert np.allclose(result.delta_map, 0.0)
        assert result.max_delta_C == pytest.approx(0.0)

    def test_within_tolerance_clean(self):
        cfg = _fdm_config()
        T_fdm = np.full((cfg.height_cells, cfg.width_cells), 50.0, dtype=np.float64)
        T_elmer = T_fdm.copy() + 3.0  # 3 deg-C offset -- within 5 deg-C tolerance

        result = compare_fields(
            fdm_field=T_fdm,
            elmer_field=T_elmer,
            fdm_config=cfg,
            tolerance_C=5.0,
        )
        assert result.is_clean
        np.testing.assert_allclose(result.delta_map, 3.0, atol=1e-10)


# ---------------------------------------------------------------------------
# VIOLATIONS with device-region hotspot
# ---------------------------------------------------------------------------


class TestDeviceRegionHotspot:
    """Disagreement in the device footprint region -> VIOLATIONS."""

    def test_device_region_hotspot(self):
        cfg = _fdm_config()
        H, W = cfg.height_cells, cfg.width_cells
        T_fdm = np.full((H, W), 45.0, dtype=np.float64)
        T_elmer = T_fdm.copy()

        # Device Q1 at (5.0, 5.0) mm with 0.5mm cells -> cell center (10, 10)
        # Footprint 5x5mm -> cells 5:15, 5:15 (10x10 = 100 cells)
        # Hotspot: entire footprint region at +75 deg-C
        T_elmer[5:15, 5:15] = 120.0

        devices = {"Q1": (5.0, 5.0)}

        result = compare_fields(
            fdm_field=T_fdm,
            elmer_field=T_elmer,
            fdm_config=cfg,
            devices=devices,
            tolerance_C=5.0,
        )

        assert not result.is_clean
        assert "device" in result.attribution
        assert result.max_delta_C > 5.0
        # Device T_j spot-check: entire footprint has 75 deg-C delta -> avg=75
        assert "Q1" in result.per_device_deltas
        assert result.per_device_deltas["Q1"] > 50.0

    def test_device_hotspot_with_copper_attribution(self):
        cfg = _fdm_config()
        H, W = cfg.height_cells, cfg.width_cells
        T_fdm = np.full((H, W), 45.0, dtype=np.float64)
        T_elmer = T_fdm.copy()

        # Hotspot far from device
        T_elmer[0:3, 0:3] = 100.0

        copper = np.ones((H, W), dtype=np.float64) * 0.5  # copper everywhere

        devices = {"Q1": (5.0, 5.0)}

        result = compare_fields(
            fdm_field=T_fdm,
            elmer_field=T_elmer,
            fdm_config=cfg,
            devices=devices,
            copper_grid=copper,
            tolerance_C=5.0,
        )

        assert not result.is_clean
        assert "copper_plane" in result.attribution


# ---------------------------------------------------------------------------
# Far-field-only disagreement
# ---------------------------------------------------------------------------


class TestFarFieldDisagreement:
    """Disagreement only in the far-field (away from devices and heatsink)."""

    def test_far_field_only(self):
        cfg = _fdm_config()
        H, W = cfg.height_cells, cfg.width_cells
        T_fdm = np.full((H, W), 45.0, dtype=np.float64)
        T_elmer = T_fdm.copy()

        # Inject far-field disagreement (bottom rows, far from TOP heatsink)
        T_elmer[0:3, :] = 60.0

        result = compare_fields(
            fdm_field=T_fdm,
            elmer_field=T_elmer,
            fdm_config=cfg,
            tolerance_C=5.0,
        )

        assert not result.is_clean
        assert "far_field" in result.attribution

    def test_near_heatsink_disagreement(self):
        cfg = _fdm_config(H=20, W=30, hs="TOP")
        H, W = cfg.height_cells, cfg.width_cells
        T_fdm = np.full((H, W), 45.0, dtype=np.float64)
        T_elmer = T_fdm.copy()

        # Inject disagreement at top edge (near TOP heatsink)
        T_elmer[17:20, :] = 70.0

        result = compare_fields(
            fdm_field=T_fdm,
            elmer_field=T_elmer,
            fdm_config=cfg,
            tolerance_C=5.0,
        )

        assert not result.is_clean
        assert "near_heatsink" in result.attribution


# ---------------------------------------------------------------------------
# Per-device T_j spot-checks (R4)
# ---------------------------------------------------------------------------


class TestDeviceSpotChecks:
    """Device T_j deltas extracted from area-averaged comparison."""

    def test_per_device_deltas(self):
        cfg = _fdm_config()
        H, W = cfg.height_cells, cfg.width_cells
        T_fdm = np.full((H, W), 45.0, dtype=np.float64)
        T_elmer = T_fdm.copy()

        # Device Q1 at (5.0, 5.0) mm -> footprint cells 5:15, 5:15
        # Inject delta into the FULL footprint -> 100 cells at +10 deg-C -> avg=10
        T_elmer[5:15, 5:15] = 55.0

        devices = {"Q1": (5.0, 5.0)}

        result = compare_fields(
            fdm_field=T_fdm,
            elmer_field=T_elmer,
            fdm_config=cfg,
            devices=devices,
            tolerance_C=5.0,
        )

        assert "Q1" in result.per_device_deltas
        assert abs(result.per_device_deltas["Q1"] - 10.0) < 0.01


# ---------------------------------------------------------------------------
# Shape mismatch
# ---------------------------------------------------------------------------


class TestShapeMismatch:
    """Comparison fails when FDM and Elmer fields have different shapes."""

    def test_shape_mismatch(self):
        cfg = _fdm_config()
        T_fdm = np.zeros((10, 20), dtype=np.float64)
        T_elmer = np.zeros((20, 10), dtype=np.float64)

        result = compare_fields(
            fdm_field=T_fdm,
            elmer_field=T_elmer,
            fdm_config=cfg,
            tolerance_C=5.0,
        )
        assert not result.is_clean
        assert "shape mismatch" in result.error_message.lower()


# ---------------------------------------------------------------------------
# Zero-length field
# ---------------------------------------------------------------------------


class TestTrivialFields:
    """Trivial 1x1 fields should work."""

    def test_trivial_clean(self):
        cfg = _fdm_config(H=1, W=1)
        T = np.array([[42.0]], dtype=np.float64)

        result = compare_fields(
            fdm_field=T,
            elmer_field=T.copy(),
            fdm_config=cfg,
            tolerance_C=1.0,
        )
        assert result.is_clean
