"""R1b: performance A/B for the Wave-4 Phase 2 contract layer.

Both arms assert parity **in-harness**: a speedup measured against a
kernel that computes something else is not a speedup. Every workload
below therefore compares the two results through the R1a signature
before reporting a ratio.

Sizes are pinned as module constants and the differential asserts it
covers all of them (``test_perf_harness_parameters_are_covered``), so no
benchmark can run at a scale parity was never measured at -- the failure
mode that made PR #714 pass on macOS and fail on Linux CI.
"""

from __future__ import annotations

import random
import time

import pytest

from temper_placer.core import manufacturing as prod_mf
from temper_placer.core import net_classification as prod_nc
from temper_placer.core import units as prod_units
from temper_placer.core.board import Rect as ProdRect
from temper_placer.core.netlist import build_adjacency_matrix as prod_adjacency
from tests.wave4_phase2 import _core_py_oracle as oracle
from tests.wave4_phase2._sig import assert_same

PERF_NAME_COUNT = 4000
PERF_PIN_COUNT = 600
PERF_COMPONENT_COUNT = 400
PERF_NET_COUNT = 1200
PERF_RECT_COUNT = 4000
PERF_SCALAR_COUNT = 20000

_REPEATS = 3


def _best(fn, repeats: int = _REPEATS) -> tuple[float, object]:
    """Best-of-N wall time, plus the result, so parity can be asserted."""
    best = float("inf")
    result = None
    for _ in range(repeats):
        t0 = time.perf_counter()
        result = fn()
        best = min(best, time.perf_counter() - t0)
    return best, result


def _report(label: str, py_s: float, rs_s: float) -> str:
    ratio = py_s / rs_s if rs_s > 0 else float("inf")
    line = f"{label}: python {py_s * 1e3:.3f} ms, rust {rs_s * 1e3:.3f} ms, {ratio:.2f}x"
    print(line)
    return line


def _names(n: int) -> list[str]:
    rng = random.Random(4242)
    stems = ["GND", "VCC", "+3V3", "AC_L", "SDA", "SCL", "PE", "DC_BUS+", "SW_NODE", "MISO"]
    return [f"{rng.choice(stems)}{rng.choice(['', '_1', '2', '_BUS', 'X'])}" for _ in range(n)]


def test_perf_net_classification():
    names = _names(PERF_NAME_COUNT)
    py_s, py_r = _best(lambda: [oracle.classify_net_type(n) for n in names])
    rs_s, rs_r = _best(lambda: [prod_nc.classify_net_type(n) for n in names])
    assert_same(rs_r, py_r, "classify_net_type parity")
    _report(f"classify_net_type x{PERF_NAME_COUNT}", py_s, rs_s)


def test_perf_adjacency():
    from temper_placer.core.netlist import Component, Net, Netlist

    rng = random.Random(2718)
    refs = [f"U{i}" for i in range(PERF_COMPONENT_COUNT)]
    net_pin_refs = [
        [rng.choice(refs) for _ in range(rng.randint(2, 8))] for _ in range(PERF_NET_COUNT)
    ]
    prod = Netlist(
        components=[Component(ref=r, footprint="F", bounds=(1.0, 1.0)) for r in refs],
        nets=[
            Net(name=f"N{i}", pins=[(r, "1") for r in pins]) for i, pins in enumerate(net_pin_refs)
        ],
    )
    orc = oracle.make_oracle_netlist(refs, net_pin_refs)

    py_s, py_r = _best(lambda: oracle.build_adjacency_matrix(orc))
    rs_s, rs_r = _best(lambda: prod_adjacency(prod))
    assert_same(rs_r, py_r, "build_adjacency_matrix parity")
    assert py_r.sum() > 0
    _report(f"build_adjacency_matrix {PERF_COMPONENT_COUNT}x{PERF_NET_COUNT}", py_s, rs_s)


def test_perf_rect_construction():
    rng = random.Random(1618)
    args = [
        (x := rng.uniform(-100.0, 100.0), y := rng.uniform(-100.0, 100.0), x + 1.0, y + 1.0)
        for _ in range(PERF_RECT_COUNT)
    ]
    py_s, py_r = _best(lambda: [oracle.Rect.coerce(a) for a in args])
    rs_s, rs_r = _best(lambda: [ProdRect.coerce(a) for a in args])
    assert_same(rs_r, py_r, "Rect.coerce parity")
    _report(f"Rect.coerce x{PERF_RECT_COUNT}", py_s, rs_s)


def test_perf_rect_attribute_access():
    rects_py = [oracle.Rect.from_xyxy(0.0, 0.0, 1.0, 1.0) for _ in range(1000)]
    rects_rs = [ProdRect.from_xyxy(0.0, 0.0, 1.0, 1.0) for _ in range(1000)]
    py_s, py_r = _best(lambda: [r.x_min + r.y_max for r in rects_py])
    rs_s, rs_r = _best(lambda: [r.x_min + r.y_max for r in rects_rs])
    assert_same(rs_r, py_r, "attribute access parity")
    _report("Rect attribute access x1000", py_s, rs_s)


@pytest.mark.parametrize(
    ("label", "py_fn", "rs_fn"),
    [
        ("deg_to_rad", oracle.deg_to_rad, prod_units.deg_to_rad),
        ("rad_to_deg", oracle.rad_to_deg, prod_units.rad_to_deg),
    ],
)
def test_perf_units_scalars(label, py_fn, rs_fn):
    rng = random.Random(11)
    xs = [rng.uniform(-1e4, 1e4) for _ in range(PERF_SCALAR_COUNT)]
    py_s, py_r = _best(lambda: [py_fn(x) for x in xs])
    rs_s, rs_r = _best(lambda: [rs_fn(x) for x in xs])
    assert_same(rs_r, py_r, f"{label} parity")
    _report(f"{label} x{PERF_SCALAR_COUNT}", py_s, rs_s)


def test_perf_inflated_clearance():
    rng = random.Random(13)
    xs = [(rng.uniform(0.0, 1.0), rng.uniform(0.0, 0.3)) for _ in range(PERF_SCALAR_COUNT)]
    py_s, py_r = _best(lambda: [oracle.inflated_clearance(a, b) for a, b in xs])
    rs_s, rs_r = _best(lambda: [prod_mf.inflated_clearance(a, b) for a, b in xs])
    assert_same(rs_r, py_r, "inflated_clearance parity")
    _report(f"inflated_clearance x{PERF_SCALAR_COUNT}", py_s, rs_s)
