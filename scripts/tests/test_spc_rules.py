"""Tests for Western Electric SPC rules in spc_rules.py."""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from spc_rules import (
    compute_control_limits,
    evaluate_rules,
    rule_2of3_2sigma,
    rule_3sigma,
    rule_4of5_1sigma,
    rule_8consecutive,
)


def test_compute_control_limits():
    values = [10.0, 12.0, 14.0, 16.0, 18.0]
    mean, sigma = compute_control_limits(values)
    assert mean == 14.0
    assert math.isclose(sigma, math.sqrt(10.0), rel_tol=1e-9)


def test_compute_control_limits_single_value():
    mean, sigma = compute_control_limits([5.0])
    assert mean == 5.0
    assert sigma == 0.0


def test_compute_control_limits_all_same():
    values = [7.0, 7.0, 7.0, 7.0]
    mean, sigma = compute_control_limits(values)
    assert mean == 7.0
    assert sigma == 0.0


def test_rule_3sigma_fires():
    values = [0.0] * 10 + [100.0]
    mean, sigma = compute_control_limits(values)
    assert sigma > 0
    assert rule_3sigma(values, mean, sigma) is True


def test_rule_3sigma_no_fire():
    values = [10.0, 11.0, 10.0, 11.0, 10.0, 11.0, 10.0, 11.0, 10.0]
    mean, sigma = compute_control_limits(values)
    assert rule_3sigma(values, mean, sigma) is False


def test_rule_3sigma_insufficient_data():
    assert rule_3sigma([5.0], 5.0, 1.0) is False
    assert rule_3sigma([], 0.0, 1.0) is False


def test_rule_3sigma_zero_sigma():
    assert rule_3sigma([5.0, 5.0, 5.0], 5.0, 0.0) is False


def test_rule_2of3_2sigma_fires():
    values = [10.0] * 20 + [50.0, 50.0, 10.0]
    mean, sigma = compute_control_limits(values)
    assert sigma > 0
    assert rule_2of3_2sigma(values, mean, sigma) is True


def test_rule_2of3_2sigma_no_fire():
    values = [10.0, 11.0, 10.0, 11.0, 10.0, 11.0, 10.0, 11.0, 10.0]
    mean, sigma = compute_control_limits(values)
    assert rule_2of3_2sigma(values, mean, sigma) is False


def test_rule_2of3_2sigma_insufficient_data():
    assert rule_2of3_2sigma([10.0, 12.0], 10.0, 1.0) is False
    assert rule_2of3_2sigma([], 10.0, 1.0) is False


def test_rule_4of5_1sigma_fires():
    values = [10.0] * 20 + [30.0, 30.0, 30.0, 30.0, 10.0]
    mean, sigma = compute_control_limits(values)
    assert sigma > 0
    assert rule_4of5_1sigma(values, mean, sigma) is True


def test_rule_4of5_1sigma_no_fire():
    values = [10.0, 11.0, 10.0, 11.0, 10.0, 11.0, 10.0, 11.0, 10.0]
    mean, sigma = compute_control_limits(values)
    assert rule_4of5_1sigma(values, mean, sigma) is False


def test_rule_4of5_1sigma_insufficient_data():
    assert rule_4of5_1sigma([10.0, 12.0, 14.0, 16.0], 10.0, 1.0) is False


def test_rule_8consecutive_fires():
    values = [10.0] * 8 + [12.0] * 8
    mean = sum(values) / len(values)
    assert rule_8consecutive(values, mean) is True


def test_rule_8consecutive_no_fire():
    values = [10.0, 11.0, 10.0, 11.0, 10.0, 11.0, 10.0, 11.0]
    mean = sum(values) / len(values)
    assert rule_8consecutive(values, mean) is False


def test_rule_8consecutive_all_equal_mean():
    values = [10.0] * 8
    mean = 10.0
    assert rule_8consecutive(values, mean) is False


def test_rule_8consecutive_insufficient_data():
    assert rule_8consecutive([10.0] * 7, 10.0) is False


def test_evaluate_rules_stable():
    values = [10.0, 11.0, 10.0, 11.0, 10.0, 11.0, 10.0, 11.0, 10.0]
    result = evaluate_rules(values)
    assert not any(result.values())


def test_evaluate_rules_insufficient_data():
    result = evaluate_rules([5.0])
    assert not any(result.values())


def test_evaluate_rules_3sigma_violation():
    values = [0.0] * 10 + [100.0]
    result = evaluate_rules(values)
    assert result["rule_3sigma"] is True


def test_evaluate_rules_2of3_2sigma_violation():
    values = [10.0] * 20 + [50.0, 50.0, 10.0]
    result = evaluate_rules(values)
    assert result["rule_2of3_2sigma"] is True


def test_evaluate_rules_4of5_1sigma_violation():
    values = [10.0] * 20 + [30.0, 30.0, 30.0, 30.0, 10.0]
    result = evaluate_rules(values)
    assert result["rule_4of5_1sigma"] is True


def test_evaluate_rules_8consecutive_violation():
    values = [10.0] * 8 + [12.0] * 8
    result = evaluate_rules(values)
    assert result["rule_8consecutive"] is True
