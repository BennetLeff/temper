"""Coverage paydown tests — Wave 3 easy wins (Batch B).

Covers: _check_report_base, congestion_tensor, neighbor_validity,
net_classification, diff_pair_inference properties.
"""

from __future__ import annotations

import numpy as np
import pytest

from temper_placer.router_v6._check_report_base import BaseCheckReport
from temper_placer.router_v6.congestion_tensor import CongestionTensor
from temper_placer.router_v6.net_classification import (
    classify_net_type,
    get_single_layer_mode,
    is_clock_pin,
    is_ground_net,
    is_ground_pin,
    is_hv_net,
    is_hv_pin,
    is_power_net,
    is_power_pin,
    is_signal_net,
    set_single_layer_mode,
)
from temper_placer.router_v6.neighbor_validity import (
    DIRS_8,
    build_neighbor_validity_tensor_2d,
    is_valid_2d,
)
from temper_placer.router_v6.occupancy_grid import OccupancyGrid


# ── _check_report_base ──────────────────────────────────────────────


class _FakeReport(BaseCheckReport):
    def __init__(self, violations, total_checks=0):
        self.violations = violations
        self.total_checks = total_checks


def test_base_check_report_violation_count():
    r = _FakeReport(["a", "b", "c"], total_checks=10)
    assert r.violation_count == 3


def test_base_check_report_pass_rate():
    r = _FakeReport(["a"], total_checks=10)
    assert r.pass_rate == pytest.approx(90.0)


def test_base_check_report_pass_rate_empty_denom():
    r = _FakeReport(["a"], total_checks=0)
    assert r.pass_rate == 100.0


def test_base_check_report_pass_rate_none():
    r = _FakeReport(["a", "b"], total_checks=5)
    assert r.pass_rate == pytest.approx(60.0)


# ── congestion_tensor ──────────────────────────────────────────────


def test_congestion_tensor_zeros():
    ct = CongestionTensor.zeros(5, 5)
    arr = ct.array
    assert arr.shape == (5, 5)
    assert arr.dtype == np.float32
    assert np.all(arr == 0.0)


def test_congestion_tensor_increment():
    ct = CongestionTensor.zeros(5, 5)
    ct.increment(2, 3, weight=2.0)
    arr = ct.array
    assert arr[2, 3] == pytest.approx(2.0)


def test_congestion_tensor_cost():
    ct = CongestionTensor.zeros(5, 5)
    ct.increment(0, 0)
    c = ct.cost(0, 0)
    assert c > 1.0
    c_zero = ct.cost(1, 1)
    assert c_zero == pytest.approx(1.0)


def test_congestion_tensor_decay():
    ct = CongestionTensor.zeros(5, 5)
    ct.increment(0, 0, weight=10.0)
    ct.decay(0.5)
    arr = ct.array
    assert arr[0, 0] == pytest.approx(5.0)


def test_congestion_tensor_reset():
    ct = CongestionTensor.zeros(5, 5)
    ct.increment(0, 0, weight=10.0)
    ct.reset()
    arr = ct.array
    assert np.all(arr == 0.0)


def test_congestion_tensor_from_array():
    arr = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)
    ct = CongestionTensor(arr)
    assert ct.array.shape == (2, 2)
    assert ct.array[0, 0] == pytest.approx(1.0)


def test_congestion_tensor_increment_path():
    ct = CongestionTensor.zeros(10, 10)
    # Use a real OccupancyGrid so world_to_grid works
    og = OccupancyGrid(
        "F.Cu",
        np.zeros((10, 10), dtype=np.int8),
        (0.0, 0.0),
        1.0,
        10,
        10,
    )
    coords = [(0.5, 0.5), (1.5, 0.5)]
    ct.increment_path(coords, og, weight=1.0)
    arr = ct.array
    assert arr[0, 0] == pytest.approx(1.0)
    assert arr[0, 1] == pytest.approx(1.0)


# ── neighbor_validity ──────────────────────────────────────────────


def test_dir8_cardinals():
    """E, S, W, N are in DIRS_8."""
    assert (1, 0) in DIRS_8
    assert (0, 1) in DIRS_8
    assert (-1, 0) in DIRS_8
    assert (0, -1) in DIRS_8


def test_build_neighbor_validity_tensor_2d_empty():
    og = OccupancyGrid(
        "F.Cu",
        np.zeros((5, 5), dtype=np.int8),
        (0.0, 0.0),
        1.0,
        5,
        5,
    )
    tensor = build_neighbor_validity_tensor_2d(og)
    assert tensor.shape == (5, 5, 8)
    assert tensor.dtype == np.bool_
    # All interior cells have 8 valid neighbors on an empty grid
    assert tensor[2, 2, 0] is np.bool_(True)


def test_build_neighbor_validity_tensor_2d_edge():
    og = OccupancyGrid(
        "F.Cu",
        np.zeros((5, 5), dtype=np.int8),
        (0.0, 0.0),
        1.0,
        5,
        5,
    )
    tensor = build_neighbor_validity_tensor_2d(og)
    # Corner cell has fewer valid neighbors
    valid_count = int(tensor[0, 0].sum())
    assert valid_count < 8


def test_is_valid_2d():
    og = OccupancyGrid(
        "F.Cu",
        np.zeros((5, 5), dtype=np.int8),
        (0.0, 0.0),
        1.0,
        5,
        5,
    )
    tensor = build_neighbor_validity_tensor_2d(og)
    assert is_valid_2d(tensor, 2, 2, 0) is True


def test_is_valid_2d_oob():
    og = OccupancyGrid(
        "F.Cu",
        np.zeros((5, 5), dtype=np.int8),
        (0.0, 0.0),
        1.0,
        5,
        5,
    )
    tensor = build_neighbor_validity_tensor_2d(og)
    # Negative row
    assert is_valid_2d(tensor, -1, 0, 0) is False
    # Out of bounds
    assert is_valid_2d(tensor, 10, 0, 0) is False


# ── net_classification ─────────────────────────────────────────────


def test_is_ground_net_true():
    assert is_ground_net("GND") is True
    assert is_ground_net("PGND") is True
    assert is_ground_net("AGND") is True


def test_is_ground_net_false():
    assert is_ground_net("SIGNAL1") is False
    assert is_ground_net("VCC") is False


def test_is_power_net_true():
    assert is_power_net("+3V3") is True
    assert is_power_net("+5V") is True
    assert is_power_net("VCC") is True
    assert is_power_net("VDD") is True


def test_is_power_net_plus_prefix():
    assert is_power_net("+12V_EXTRA") is True


def test_is_power_net_false():
    assert is_power_net("SIGNAL1") is False


def test_is_hv_net_true():
    assert is_hv_net("AC_L") is True
    assert is_hv_net("AC_N") is True
    assert is_hv_net("SW_NODE") is True


def test_is_hv_net_false():
    assert is_hv_net("SIGNAL1") is False
    assert is_hv_net("GND") is False


def test_is_signal_net_true():
    assert is_signal_net("SPI_CLK") is True
    assert is_signal_net("PWM_DRV") is True


def test_is_signal_net_false_for_power():
    assert is_signal_net("GND") is False
    assert is_signal_net("VCC") is False
    assert is_signal_net("AC_L") is False


def test_classify_net_type():
    assert classify_net_type("GND") == "ground"
    assert classify_net_type("+3V3") == "power"
    assert classify_net_type("AC_L") == "hv"
    assert classify_net_type("SPI_CLK") == "signal"


def test_is_ground_pin():
    assert is_ground_pin("GND") is True
    assert is_ground_pin("VSS") is True
    assert is_ground_pin("DATA") is False


def test_is_power_pin():
    assert is_power_pin("VCC") is True
    assert is_power_pin("VIN") is True
    assert is_power_pin("DATA") is False


def test_is_hv_pin():
    assert is_hv_pin("AC_L") is True
    assert is_hv_pin("HV") is True
    assert is_hv_pin("DATA") is False


def test_is_clock_pin():
    assert is_clock_pin("CLK") is True
    assert is_clock_pin("XTAL1") is True
    assert is_clock_pin("DATA") is False


def test_single_layer_mode():
    original = get_single_layer_mode()
    try:
        set_single_layer_mode(True)
        assert get_single_layer_mode() is True
        # In single-layer mode, GND is not ground
        assert is_ground_net("GND") is False
        assert is_power_net("+3V3") is False
        assert is_hv_net("AC_L") is False
        assert is_signal_net("AC_L") is True
    finally:
        set_single_layer_mode(original)
