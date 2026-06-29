"""Western Electric SPC rules -- pure Python, no external stats dependency."""

from __future__ import annotations

import math


def compute_control_limits(values: list[float]) -> tuple[float, float]:
    mean = sum(values) / len(values)
    n = len(values)
    if n < 2:
        return mean, 0.0
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    sigma = math.sqrt(variance) if variance > 0 else 0.0
    return mean, sigma


def rule_3sigma(values: list[float], mean: float, sigma: float) -> bool:
    if len(values) < 1 or sigma == 0:
        return False
    latest = values[-1]
    return abs(latest - mean) > 3 * sigma


def rule_2of3_2sigma(values: list[float], mean: float, sigma: float) -> bool:
    if len(values) < 3 or sigma == 0:
        return False
    last3 = values[-3:]
    upper = mean + 2 * sigma
    lower = mean - 2 * sigma
    above = sum(1 for v in last3 if v > upper)
    below = sum(1 for v in last3 if v < lower)
    return above >= 2 or below >= 2


def rule_4of5_1sigma(values: list[float], mean: float, sigma: float) -> bool:
    if len(values) < 5 or sigma == 0:
        return False
    last5 = values[-5:]
    upper = mean + sigma
    lower = mean - sigma
    above = sum(1 for v in last5 if v > upper)
    below = sum(1 for v in last5 if v < lower)
    return above >= 4 or below >= 4


def rule_8consecutive(values: list[float], mean: float) -> bool:
    if len(values) < 8:
        return False
    last8 = values[-8:]
    return all(v > mean for v in last8) or all(v < mean for v in last8)


def evaluate_rules(values: list[float]) -> dict[str, bool]:
    if len(values) < 2:
        return {
            "rule_3sigma": False,
            "rule_2of3_2sigma": False,
            "rule_4of5_1sigma": False,
            "rule_8consecutive": False,
        }
    mean, sigma = compute_control_limits(values)
    return {
        "rule_3sigma": rule_3sigma(values, mean, sigma),
        "rule_2of3_2sigma": rule_2of3_2sigma(values, mean, sigma),
        "rule_4of5_1sigma": rule_4of5_1sigma(values, mean, sigma),
        "rule_8consecutive": rule_8consecutive(values, mean),
    }
