"""Differential tests: Rust SPICE estimators vs the pure-Python reference
(temper_geometry.spice_estimators vs temper_placer.validation.spice).

The pre-migration implementations of ``estimate_loop_inductance`` and
``_infer_unit`` are pinned here as oracles (verbatim semantics,
including the shoelace accumulation order and the unit thresholds).
Any change to the Rust core or the delegation that disagrees with the
oracle fails here, bit-exactly.
"""

from __future__ import annotations

import random

from temper_placer.validation.spice import NgspiceValidator, estimate_loop_inductance


def _oracle_loop_inductance(positions, trace_height_mm):
    n = len(positions)
    area = 0.0
    for i in range(n):
        x1, y1 = positions[i]
        x2, y2 = positions[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    area = abs(area) / 2.0
    area_m2 = area * 1e-6
    mu_0 = 4 * 3.14159265359e-7
    h_m = trace_height_mm * 1e-3
    return mu_0 * area_m2 / h_m


def _oracle_infer_unit(name, value):
    name_lower = name.lower()
    if any(x in name_lower for x in ["time", "trise", "tfall", "delay", "period"]):
        if abs(value) < 1e-9:
            return "ps"
        elif abs(value) < 1e-6:
            return "ns"
        elif abs(value) < 1e-3:
            return "us"
        else:
            return "s"
    if any(x in name_lower for x in ["v_", "vce", "vgs", "vout", "vin", "voltage"]):
        return "V"
    if any(x in name_lower for x in ["i_", "iout", "iin", "current"]):
        return "mA" if abs(value) < 1e-3 else "A"
    if any(x in name_lower for x in ["e_", "eoff", "eon", "energy"]):
        if abs(value) < 1e-6:
            return "uJ"
        elif abs(value) < 1e-3:
            return "mJ"
        else:
            return "J"
    if any(x in name_lower for x in ["p_", "power", "pout", "pin"]):
        return "W"
    return ""


VALIDATOR = NgspiceValidator({})


def test_loop_inductance_matches_oracle():
    rng = random.Random(20260731)
    for _ in range(500):
        n = rng.randrange(3, 10)
        positions = [(rng.uniform(-100, 100), rng.uniform(-100, 100)) for _ in range(n)]
        h = rng.uniform(0.01, 0.2)
        refs = {f"R{i}": pos for i, pos in enumerate(positions)}
        assert estimate_loop_inductance(refs, [f"R{i}" for i in range(n)], h) == (
            _oracle_loop_inductance(positions, h)
        )


def test_loop_inductance_early_returns():
    # <3 components and missing refs return 0.0 (Python-side contract).
    assert estimate_loop_inductance({"R1": (0.0, 0.0), "R2": (1.0, 1.0)}, ["R1", "R2"]) == 0.0
    assert (
        estimate_loop_inductance({"R1": (0.0, 0.0)}, ["R1", "R2", "R3"]) == 0.0
    )


def test_infer_unit_matches_oracle():
    rng = random.Random(7)
    names = [
        "trise_time", "tfall_time", "delay_time", "period", "v_out", "vce", "vin",
        "i_out", "iin", "current_peak", "e_on", "eoff", "energy_total",
        "p_out", "p_in", "power", "some_other", "V_OUT_RAW", "Tdelay",
    ]
    for _ in range(1000):
        name = rng.choice(names) + ("" if rng.random() < 0.7 else rng.choice(["x", "_1", "2"]))
        value = 10.0 ** rng.uniform(-12, 3)
        got = VALIDATOR._infer_unit(name, value)
        assert got == _oracle_infer_unit(name, value), f"name={name!r} value={value}"
