"""Differential tests: Rust IPC-2152 ampacity model vs the pure-Python
reference (temper_constraints.ipc vs gates.py).

The pre-migration implementations of ``_ipc2152_forward`` and
``_min_width_ipc2152`` are pinned here as oracles (verbatim semantics,
including the 60-iteration bisection and banker's rounding).  Any
change to the Rust core or the delegation that disagrees with the
oracle fails here, bit-exactly.
"""

from __future__ import annotations

import random

import pytest

from temper_placer.placer.cp_sat.gates import _ipc2152_forward, _min_width_ipc2152


def _oracle_forward(width_mm, copper_oz, temp_rise_c, internal_layer):
    width_mils = width_mm * 39.3701
    thickness_mils = copper_oz * 1.37
    area_mils2 = width_mils * thickness_mils
    k_ext = 0.065
    current_ext = k_ext * (temp_rise_c**0.44) * (area_mils2**0.725)
    if internal_layer:
        return current_ext * 0.65
    return current_ext


def _oracle_min_width(current_a, copper_oz, temp_rise_c, internal_layer):
    if current_a <= 0.0:
        return 0.0
    lo, hi = 0.001, 50.0
    for _ in range(60):
        mid = (lo + hi) / 2.0
        cap = _oracle_forward(mid, copper_oz, temp_rise_c, internal_layer)
        if cap < current_a:
            lo = mid
        else:
            hi = mid
    return round(hi, 3)


def test_forward_matches_oracle_bit_exact():
    rng = random.Random(20260731)
    for _ in range(1000):
        w = rng.uniform(0.01, 50.0)
        oz = rng.uniform(0.5, 4.0)
        rise = rng.uniform(5.0, 60.0)
        internal = rng.random() < 0.5
        assert _ipc2152_forward(w, oz, rise, internal) == _oracle_forward(w, oz, rise, internal)


def test_min_width_matches_oracle_bit_exact():
    rng = random.Random(7)
    for _ in range(500):
        current = rng.uniform(0.1, 40.0)
        oz = rng.choice([0.5, 1.0, 2.0, 4.0])
        rise = rng.choice([5.0, 10.0, 20.0, 45.0])
        internal = rng.random() < 0.5
        assert _min_width_ipc2152(current, oz, rise, internal) == _oracle_min_width(
            current, oz, rise, internal
        )


def test_zero_and_negative_current():
    assert _min_width_ipc2152(0.0) == 0.0
    assert _min_width_ipc2152(-5.0) == 0.0


def test_known_operating_point():
    # 1 mm, 1 oz, 10 C external: 3.225 A forward.
    cap = _ipc2152_forward(1.0, 1.0, 10.0, False)
    assert cap == pytest.approx(3.2250131759622898, abs=0.0)
    # The 2 A threshold inverts to ~0.517 mm.
    w = _min_width_ipc2152(2.0, 1.0, 10.0, False)
    assert w == pytest.approx(0.517, abs=0.0)
