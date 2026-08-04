"""Differential tests: temper-thermal Rust T_j cross-check kernels vs
the pure-Python reference (temper_placer/physics/tj_cross_check.py,
Wave 4 Phase 4).

The pre-migration implementations are pinned here as oracles (verbatim
semantics, including: `H = height_cells * cell_size`,
`W = width_cells * cell_size`, `abs(oy + H - y)` etc. for the four
heatsink edges; and the per-device chains `T_j_fdm = T_case_fdm +
power * R_jc`, `R_total = R_jc + R_cs + R_sa`, `T_j_lumped = T_amb +
power * R_total`, `delta = abs(T_j_fdm - T_j_lumped)`,
`conservative_T_j = max(T_j_fdm, T_j_lumped)` (CPython two-arg max —
NaN in the first argument wins), `margin = T_j_max -
conservative_T_j`, `exceeds = delta > tau`).  Any change to the Rust
kernels (packages/temper-thermal/src/tj_cross_check.rs) or the Python
delegation that disagrees with the oracle fails here, bit-exactly.

Boundary note: `_area_average_temperature`'s `np.mean` is NOT migrated
— numpy's SIMD reduction is not bit-reproducible in Rust (measured
2026-08-04: no standard summation strategy matches numpy 2.3.5 on
arm64), so that call stays Python-side, argued in-source (the same
class as the KTD9 spsolve keep).
"""

from __future__ import annotations

import random
import struct

import pytest
import temper_thermal as _tt

from temper_placer.physics.tj_cross_check import (
    _distance_to_heatsink_edge,
)

# ---------------------------------------------------------------------------
# Oracles (pre-migration implementation, verbatim)
# ---------------------------------------------------------------------------


def _oracle_distance_to_heatsink_edge(position_mm, fdm_config) -> float:
    """Verbatim pre-migration distance-to-heatsink-edge."""
    x, y = position_mm
    hs = fdm_config.heatsink_edge.upper().strip()
    ox, oy = fdm_config.origin_mm
    cell = fdm_config.cell_size_mm
    H = fdm_config.height_cells * cell
    W = fdm_config.width_cells * cell

    if hs == "TOP":
        return abs(oy + H - y)
    elif hs == "BOTTOM":
        return abs(y - oy)
    elif hs == "LEFT":
        return abs(x - ox)
    elif hs == "RIGHT":
        return abs(ox + W - x)
    return 0.0


def _oracle_device_cross_check(
    T_case_fdm: float,
    power: float,
    R_jc: float,
    R_cs: float,
    R_sa: float,
    T_amb: float,
    T_j_max: float,
    tau: float,
):
    """Verbatim pre-migration per-device cross-check arithmetic."""
    T_j_fdm = T_case_fdm + power * R_jc
    R_total = R_jc + R_cs + R_sa
    T_j_lumped = T_amb + power * R_total
    delta = abs(T_j_fdm - T_j_lumped)
    conservative_T_j = max(T_j_fdm, T_j_lumped)
    margin = T_j_max - conservative_T_j
    exceeds = delta > tau
    return T_j_fdm, T_j_lumped, delta, conservative_T_j, margin, exceeds


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bits(x: float) -> str:
    return struct.pack(">d", x).hex()


class _Cfg:
    """Minimal stand-in exposing the fdm_config attributes the
    distance oracle reads."""

    def __init__(self, edge, ox, oy, cell, h, w):
        self.heatsink_edge = edge
        self.origin_mm = (ox, oy)
        self.cell_size_mm = cell
        self.height_cells = h
        self.width_cells = w


_EDGE_CODES = {"TOP": 0, "BOTTOM": 1, "LEFT": 2, "RIGHT": 3}


# ---------------------------------------------------------------------------
# Direct kernel pins
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(8))
def test_direct_distance_randomized(seed):
    rng = random.Random(seed)
    for _ in range(50):
        h, w = rng.randint(5, 40), rng.randint(5, 40)
        cell = rng.choice([0.5, 1.0, 2.0, 0.25])
        ox, oy = rng.choice([0.0, -1.5, 3.0]), rng.choice([0.0, -2.0])
        edge = rng.choice(["TOP", "BOTTOM", "LEFT", "RIGHT", "NORTH"])
        x, y = rng.uniform(-20.0, 100.0), rng.uniform(-20.0, 100.0)
        cfg = _Cfg(edge, ox, oy, cell, h, w)
        code = _EDGE_CODES.get(edge, 99)
        got = _tt.distance_to_heatsink_edge_py(x, y, ox, oy, cell, h, w, code)
        want = _oracle_distance_to_heatsink_edge((x, y), cfg)
        assert _bits(got) == _bits(want), f"seed {seed}: rust={got!r} oracle={want!r}"


def test_direct_distance_known():
    assert _tt.distance_to_heatsink_edge_py(5.0, 3.0, 0.0, 0.0, 1.0, 20, 20, 0) == 17.0
    assert _tt.distance_to_heatsink_edge_py(5.0, 3.0, 0.0, 0.0, 1.0, 20, 20, 1) == 3.0
    assert _tt.distance_to_heatsink_edge_py(5.0, 3.0, 0.0, 0.0, 1.0, 20, 20, 2) == 5.0
    assert _tt.distance_to_heatsink_edge_py(5.0, 3.0, 0.0, 0.0, 1.0, 20, 20, 3) == 15.0
    assert _tt.distance_to_heatsink_edge_py(5.0, 3.0, 0.0, 0.0, 1.0, 20, 20, 99) == 0.0


@pytest.mark.parametrize("seed", range(8))
def test_direct_device_check_randomized(seed):
    rng = random.Random(seed)
    for _ in range(50):
        t_case = rng.choice([rng.uniform(20.0, 200.0), float("nan")])
        power = rng.choice([rng.uniform(0.0, 100.0), 0.0, float("nan")])
        r_jc = rng.choice([rng.uniform(0.1, 2.0), float("nan")])
        r_cs = rng.uniform(0.0, 1.0)
        r_sa = rng.uniform(0.0, 2.0)
        t_amb = rng.uniform(20.0, 60.0)
        t_j_max = rng.choice([125.0, 150.0, 175.0])
        tau = rng.choice([1.0, 5.0, 10.0])
        got = _tt.device_cross_check_py(t_case, power, r_jc, r_cs, r_sa, t_amb, t_j_max, tau)
        want = _oracle_device_cross_check(t_case, power, r_jc, r_cs, r_sa, t_amb, t_j_max, tau)
        for g, w in zip(got, want[:5]):
            assert _bits(g) == _bits(w), f"seed {seed}: rust={got} oracle={want}"
        assert got[5] is want[5]


def test_direct_device_check_conservative_nan():
    # max(T_j_fdm, nan) = T_j_fdm — the optimistic estimate is NOT the
    # conservative one when the lumped estimate is NaN.
    got = _tt.device_cross_check_py(50.0, 5.0, 0.6, 0.25, float("nan"), 40.0, 150.0, 5.0)
    want = _oracle_device_cross_check(50.0, 5.0, 0.6, 0.25, float("nan"), 40.0, 150.0, 5.0)
    assert _bits(got[3]) == _bits(want[3])
    assert got[3] == 53.0


# ---------------------------------------------------------------------------
# Module-level delegation pins
# ---------------------------------------------------------------------------


def test_module_distance_delegation():
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig

    cfg = ThermalFDMConfig(cell_size_mm=1.0, origin_mm=(0.0, 0.0), height_cells=20, width_cells=20, heatsink_edge="BOTTOM")
    got = _distance_to_heatsink_edge((5.0, 3.0), cfg)
    want = _oracle_distance_to_heatsink_edge((5.0, 3.0), cfg)
    assert _bits(got) == _bits(want)
    assert got == 3.0
