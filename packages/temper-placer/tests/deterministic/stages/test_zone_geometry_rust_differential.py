"""Differential test: deterministic zone_geometry compute, Rust vs oracle.

Wave 4, **Phase 5, first slice** (deterministic leaf stages). The pure
compute of ``temper_placer/deterministic/stages/zone_geometry.py`` moves
to the ``temper-design-bundle`` crate
(``temper_design_bundle_python.deterministic_stages``); the Python module
becomes a delegation shim (``Zone`` stays a Python frozen dataclass; the
boundary crosses names + flat bounds). The pre-migration implementation is
pinned VERBATIM as the oracle (``_zone_geometry_py_oracle.py``).

Numerical traps pinned here:
- the 4-zone layout derives every boundary from ``board_width * 0.3`` /
  ``* 0.6`` / ``* 0.9`` with the oracle's exact expression order (each
  subsequent boundary reuses the previous product, not a fresh multiply);
- the config dict branch scales ``bounds_ratio`` by the board dimensions
  with ``ratio[i] * board_dim`` in the oracle's order;
- empty/degenerate boards are guarded by the stage's ``run`` (stays
  Python); the layout kernel itself is total for finite dimensions.
"""

from __future__ import annotations

import random

import pytest
import temper_design_bundle_python as _tdb

import tests.deterministic.stages._zone_geometry_py_oracle as _oracle
from tests.core._contract_canon import canon

_RS = _tdb.deterministic_stages
RS_LAYOUT = _RS.define_zone_layout
RS_SCALE = _RS.scale_zone_bounds


def _zones_to_tuples(zones):
    """(name, xmin, ymin, xmax, ymax) per zone, oracle order."""
    return [(z.name, z.bounds[0][0], z.bounds[0][1], z.bounds[1][0], z.bounds[1][1]) for z in zones]


def test_layout_4_zone_structure():
    """The canonical 100x100 board yields the 4 MVP-3 zones."""
    exp = _zones_to_tuples(_oracle.define_zone_layout(100.0, 100.0))
    got = list(RS_LAYOUT(100.0, 100.0))
    assert canon(exp) == canon(got)
    assert [z[0] for z in exp] == ["HV", "Power", "Signal", "MCU"]


def test_layout_boundaries():
    """30% / 60% / 90% boundaries, exact product order."""
    exp = _zones_to_tuples(_oracle.define_zone_layout(100.0, 150.0))
    got = list(RS_LAYOUT(100.0, 150.0))
    assert canon(exp) == canon(got)
    # HV: 0..30, Power: 30..60, Signal: 60..90, MCU: 90..100
    assert exp[0][1] == 0.0 and exp[0][3] == 30.0
    assert exp[1][1] == 30.0 and exp[1][3] == 60.0
    assert exp[2][1] == 60.0 and exp[2][3] == 90.0
    assert exp[3][1] == 90.0 and exp[3][3] == 100.0


def test_layout_randomized():
    rng = random.Random(8)
    for _ in range(80):
        w = rng.uniform(1.0, 500.0)
        h = rng.uniform(1.0, 500.0)
        exp = _zones_to_tuples(_oracle.define_zone_layout(w, h))
        got = list(RS_LAYOUT(w, h))
        assert canon(exp) == canon(got)


def test_layout_non_standard_dimensions():
    """Odd dimensions and floats keep exact product semantics."""
    for w, h in [(1.0, 1.0), (0.5, 3.7), (2 ** 0.5, 7.0 / 3.0), (123.456, 0.001)]:
        exp = _zones_to_tuples(_oracle.define_zone_layout(w, h))
        got = list(RS_LAYOUT(w, h))
        assert canon(exp) == canon(got)


def test_scale_zone_bounds_dict_branch():
    """The bounds_ratio dict branch: ratio[i] * board_dim, in order."""
    rng = random.Random(33)
    for _ in range(80):
        name = f"Z{rng.randrange(100)}"
        ratio = [rng.uniform(0, 1) for _ in range(4)]
        w = rng.uniform(1.0, 400.0)
        h = rng.uniform(1.0, 400.0)
        exp = _oracle.scale_zone_bounds_ratio(name, ratio, w, h)
        got = RS_SCALE(name, ratio[0], ratio[1], ratio[2], ratio[3], w, h)
        flat_exp = (exp.bounds[0][0], exp.bounds[0][1], exp.bounds[1][0], exp.bounds[1][1])
        assert canon(flat_exp) == canon(got)
        assert exp.name == name


def test_scale_zone_bounds_default_ratio():
    """The default ratio [0, 0, 1, 1] reproduces the full board."""
    got = RS_SCALE("ALL", 0.0, 0.0, 1.0, 1.0, 200.0, 100.0)
    assert canon(got) == canon((0.0, 0.0, 200.0, 100.0))
