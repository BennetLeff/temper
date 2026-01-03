"""Tests for DRC validation module."""

import numpy as np
import pytest

from temper_placer.routing.drc import (
    CLASS_DEFAULT,
    CLASS_HV,
    CLASS_LV,
    check_class_clearance,
    compute_drc_margin,
    get_asymmetric_clearance,
    get_class_id,
)


class TestComputeDrcMargin:
    """Test DRC margin computation."""

    def test_basic_margin(self):
        margin = compute_drc_margin(required_clearance=0.2, trace_width=0.2, cell_size=1.0)
        assert margin == pytest.approx(0.3)

    def test_no_cell_size_contribution(self):
        margin = compute_drc_margin(required_clearance=0.2, trace_width=0.2)
        assert margin == pytest.approx(0.3)

    def test_larger_clearance(self):
        margin = compute_drc_margin(required_clearance=0.5, trace_width=0.3)
        assert margin == pytest.approx(0.65)

    def test_narrow_trace(self):
        margin = compute_drc_margin(required_clearance=0.2, trace_width=0.1)
        assert margin == pytest.approx(0.25)


class TestGetClassId:
    """Test net class ID assignment."""

    def test_none_rules(self):
        assert get_class_id(None) == CLASS_DEFAULT

    def test_low_voltage_rules(self):
        class MockRules:
            voltage_v = 5.0
            creepage_mm = 0.2

        rules = MockRules()
        assert get_class_id(rules) == CLASS_LV

    def test_high_voltage_rules(self):
        class MockRules:
            voltage_v = 400.0
            creepage_mm = 2.5

        rules = MockRules()
        assert get_class_id(rules) == CLASS_HV

    def test_high_creepage_without_voltage(self):
        class MockRules:
            creepage_mm = 3.0

        rules = MockRules()
        assert get_class_id(rules) == CLASS_HV


class TestGetAsymmetricClearance:
    """Test asymmetric clearance between classes."""

    def test_hv_to_lv(self):
        assert get_asymmetric_clearance(CLASS_HV, CLASS_LV) == 8.0
        assert get_asymmetric_clearance(CLASS_LV, CLASS_HV) == 8.0

    def test_hv_to_default(self):
        assert get_asymmetric_clearance(CLASS_HV, CLASS_DEFAULT) == 8.0
        assert get_asymmetric_clearance(CLASS_DEFAULT, CLASS_HV) == 8.0

    def test_hv_to_hv(self):
        assert get_asymmetric_clearance(CLASS_HV, CLASS_HV) == 2.5

    def test_lv_to_lv(self):
        assert get_asymmetric_clearance(CLASS_LV, CLASS_LV) == 0.2

    def test_default_to_default(self):
        assert get_asymmetric_clearance(CLASS_DEFAULT, CLASS_DEFAULT) == 0.2

    def test_custom_min_clearance(self):
        assert get_asymmetric_clearance(CLASS_LV, CLASS_LV, min_clearance=0.3) == 0.3


class TestCheckClassClearance:
    """Test class clearance checking."""

    def test_default_class_always_safe(self):
        grid = np.zeros((10, 10, 1), dtype=np.int32)
        assert check_class_clearance(5, 5, 0, CLASS_DEFAULT, grid, 1.0) is True

    def test_empty_grid_safe(self):
        grid = np.zeros((10, 10, 1), dtype=np.int32)
        assert check_class_clearance(5, 5, 0, CLASS_HV, grid, 1.0) is True

    def test_same_class_safe(self):
        grid = np.zeros((10, 10, 1), dtype=np.int32)
        grid[5, 5, 0] = CLASS_HV
        assert check_class_clearance(5, 5, 0, CLASS_HV, grid, 1.0) is True

    def test_different_class_violation(self):
        grid = np.zeros((10, 10, 1), dtype=np.int32)
        grid[5, 5, 0] = CLASS_LV
        assert check_class_clearance(5, 5, 0, CLASS_HV, grid, 1.0) is False

    def test_adjacent_hv_lv_violation(self):
        grid = np.zeros((10, 10, 1), dtype=np.int32)
        grid[6, 5, 0] = CLASS_LV
        assert check_class_clearance(5, 5, 0, CLASS_HV, grid, 1.0) is False

    def test_hv_lv_far_apart_safe(self):
        grid = np.zeros((10, 10, 1), dtype=np.int32)
        grid[0, 0, 0] = CLASS_LV
        assert check_class_clearance(9, 9, 0, CLASS_HV, grid, 1.0) is True

    def test_layer_isolation(self):
        grid = np.zeros((10, 10, 2), dtype=np.int32)
        grid[5, 5, 1] = CLASS_LV
        assert check_class_clearance(5, 5, 0, CLASS_HV, grid, 1.0) is True
        assert check_class_clearance(5, 5, 1, CLASS_HV, grid, 1.0) is False

    def test_out_of_bounds_coordinate(self):
        grid = np.zeros((10, 10, 1), dtype=np.int32)
        assert check_class_clearance(-1, 5, 0, CLASS_HV, grid, 1.0) is True

    def test_hv_hv_reduced_clearance(self):
        grid = np.zeros((10, 10, 1), dtype=np.int32)
        grid[0, 2, 0] = CLASS_LV
        assert check_class_clearance(0, 0, 0, CLASS_HV, grid, 1.0) is False

    def test_hv_hv_far_apart_safe(self):
        grid = np.zeros((10, 10, 1), dtype=np.int32)
        grid[0, 0, 0] = CLASS_HV
        assert check_class_clearance(5, 5, 0, CLASS_HV, grid, 1.0) is True


class TestClassConstants:
    """Test class constant values."""

    def test_class_default_value(self):
        assert CLASS_DEFAULT == 0

    def test_class_hv_value(self):
        assert CLASS_HV == 1

    def test_class_lv_value(self):
        assert CLASS_LV == 2

    def test_class_ordering(self):
        assert CLASS_DEFAULT < CLASS_HV < CLASS_LV
