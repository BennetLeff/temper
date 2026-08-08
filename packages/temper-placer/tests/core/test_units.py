"""Tests for core.units module."""

import numpy as np
import pytest

from temper_placer.core.units import (
    CellIndex,
    Degrees,
    LayerIndex,
    Millimeters,
    NetId,
    Radians,
    cell_to_mm,
    deg_to_rad,
    distance_mm,
    is_valid_layer,
    is_valid_net_id,
    manhattan_distance_mm,
    mm_to_cell,
    rad_to_deg,
)


class TestAngleConversions:
    """Tests for deg_to_rad and rad_to_deg."""

    def test_deg_to_rad_zero(self):
        assert deg_to_rad(0.0) == 0.0

    def test_deg_to_rad_180(self):
        result = deg_to_rad(180.0)
        assert np.allclose(result, np.pi)

    def test_deg_to_rad_360(self):
        result = deg_to_rad(360.0)
        assert np.allclose(result, 2 * np.pi)

    def test_rad_to_deg_zero(self):
        assert rad_to_deg(0.0) == 0.0

    def test_rad_to_deg_pi(self):
        result = rad_to_deg(np.pi)
        assert np.allclose(result, 180.0)

    def test_rad_to_deg_2pi(self):
        result = rad_to_deg(2 * np.pi)
        assert np.allclose(result, 360.0)

    def test_roundtrip_deg(self):
        for deg in [0, 45, 90, 135, 180, 270, 360]:
            rad = deg_to_rad(float(deg))
            back = rad_to_deg(rad)
            assert np.allclose(back, float(deg), atol=1e-10)

    def test_deg_to_rad_array(self):
        degs = np.array([0.0, 90.0, 180.0, 270.0, 360.0])
        rads = deg_to_rad(degs)
        expected = degs * np.pi / 180.0
        assert np.allclose(rads, expected)

    def test_rad_to_deg_array(self):
        rads = np.array([0.0, np.pi / 2, np.pi, 3 * np.pi / 2, 2 * np.pi])
        degs = rad_to_deg(rads)
        expected = rads * 180.0 / np.pi
        assert np.allclose(degs, expected)


class TestSpatialConversions:
    """Tests for mm_to_cell, cell_to_mm, distance_mm, manhattan_distance_mm."""

    CELL = Millimeters(0.1)

    def test_mm_to_cell_zero(self):
        assert mm_to_cell(Millimeters(0.0), self.CELL) == 0

    def test_mm_to_cell_positive(self):
        cell = mm_to_cell(Millimeters(10.5), self.CELL)
        assert cell == 105

    def test_mm_to_cell_fractional(self):
        cell = mm_to_cell(Millimeters(10.0), Millimeters(0.25))
        assert cell == 40

    def test_cell_to_mm_zero(self):
        mm = cell_to_mm(CellIndex(0), self.CELL)
        assert mm == 0.0

    def test_cell_to_mm_positive(self):
        mm = cell_to_mm(CellIndex(105), self.CELL)
        assert mm == pytest.approx(10.5)

    def test_cell_mm_roundtrip(self):
        # Use a value that divides evenly by cell size to avoid truncation loss
        original_mm = Millimeters(10.0)
        cell = mm_to_cell(original_mm, self.CELL)
        back_mm = cell_to_mm(cell, self.CELL)
        assert back_mm == pytest.approx(original_mm)

    def test_distance_mm_same_point(self):
        d = distance_mm(Millimeters(0.0), Millimeters(0.0), Millimeters(0.0), Millimeters(0.0))
        assert d == 0.0

    def test_distance_mm_3_4_5_triangle(self):
        d = distance_mm(Millimeters(0.0), Millimeters(0.0), Millimeters(3.0), Millimeters(4.0))
        assert d == pytest.approx(5.0)

    def test_distance_mm_horizontal(self):
        d = distance_mm(Millimeters(0.0), Millimeters(0.0), Millimeters(10.0), Millimeters(0.0))
        assert d == pytest.approx(10.0)

    def test_manhattan_distance_mm(self):
        d = manhattan_distance_mm(
            Millimeters(1.0), Millimeters(2.0), Millimeters(4.0), Millimeters(6.0)
        )
        assert d == pytest.approx(7.0)  # |4-1| + |6-2| = 3 + 4 = 7

    def test_manhattan_distance_mm_zero(self):
        d = manhattan_distance_mm(
            Millimeters(5.0), Millimeters(5.0), Millimeters(5.0), Millimeters(5.0)
        )
        assert d == 0.0


class TestTypeGuards:
    """Tests for is_valid_layer and is_valid_net_id."""

    def test_is_valid_layer_top(self):
        assert is_valid_layer(LayerIndex(0)) is True

    def test_is_valid_layer_bottom(self):
        assert is_valid_layer(LayerIndex(3)) is True

    def test_is_valid_layer_out_of_range(self):
        assert is_valid_layer(LayerIndex(4)) is False

    def test_is_valid_layer_negative(self):
        assert is_valid_layer(LayerIndex(-1)) is False

    def test_is_valid_layer_custom_max(self):
        assert is_valid_layer(LayerIndex(5), max_layers=6) is True
        assert is_valid_layer(LayerIndex(6), max_layers=6) is False

    def test_is_valid_net_id_positive(self):
        assert is_valid_net_id(NetId(1)) is True

    def test_is_valid_net_id_zero(self):
        assert is_valid_net_id(NetId(0)) is True

    def test_is_valid_net_id_negative(self):
        assert is_valid_net_id(NetId(-1)) is False  # conflict marker

    def test_is_valid_net_id_negative_obstacle(self):
        assert is_valid_net_id(NetId(-2)) is False  # obstacle marker
