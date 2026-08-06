"""Differential test: deterministic _phase_validation compute, Rust vs oracle.

Wave 4, **Phase 5, final leaves**. The
``_PhaseValidationMixin.find_critical_bottleneck_violations`` kernel of
``temper_placer/deterministic/stages/_phase_validation.py`` moves to the
``temper-design-bundle`` crate
(``temper_design_bundle_python.deterministic_phase``); the Python method
becomes a delegation shim. The pre-migration implementation is pinned VERBATIM
as the oracle (``_phase_validation_py_oracle.py``).

VERBATIM SUBTLETY pinned here (anti-vacuity): the violation dict's ``severity``
reads ``bn.severity`` where ``bn`` is the loop variable of the FIRST bottleneck
loop — i.e. the severity of the LAST bottleneck in the input list, not the
severity of the matched cell. ``test_radius_severity_reads_last_bottleneck``
pins this divergence from the "obviously correct" ``cell_bn.severity``.

Other pins:
- grid coords are ``int(math.floor((float(x_mm) * 1000.0) / cell_um))`` —
  ``float()`` coercion, then ``* 1000.0``, then ``/ cell_um``, then floor
  (negative coordinates floor toward -inf);
- out-of-grid cells are skipped; per cell the FIRST bottleneck wins on score
  ties; placements iterate in dict insertion order.
"""

from __future__ import annotations

import random

import pytest
import temper_design_bundle_python as _tdb
import tests.deterministic.stages._phase_validation_py_oracle as _oracle
from tests.core._contract_canon import canon

# Rust symbol under test -- must exist or this file fails to collect (RED).
_DP = _tdb.deterministic_phase
RS_VIOL = _DP.find_critical_bottleneck_violations_py


class _FakeBn:
    def __init__(self, x, y, layer, severity, score):
        self.x = x
        self.y = y
        self.layer = layer
        self.severity = severity
        self.score = score


def _flat(bottlenecks):
    return [(bn.x, bn.y, bn.layer, bn.severity, bn.score) for bn in bottlenecks]


def _assert_equal(placements, bottlenecks, cell_um, width, height):
    exp = _oracle.find_critical_bottleneck_violations(
        placements, bottlenecks, cell_um, width, height
    )
    got = RS_VIOL(placements, _flat(bottlenecks), cell_um, width, height)
    assert canon(got) == canon(exp), (
        f"violation divergence placements={placements} "
        f"bottlenecks={[(bn.x, bn.y, bn.layer, bn.severity) for bn in bottlenecks]} "
        f"cell_um={cell_um} size=({width},{height}): {canon(got)} vs {canon(exp)}"
    )


def _bn(x, y, layer="F.Cu", severity="CRITICAL", score=1.0):
    return _FakeBn(x, y, layer, severity, score)


def test_violations_basic():
    _assert_equal({"R1": (0.5, 0.5)}, [_bn(0, 0)], 1000.0, 5, 5)


def test_violations_no_critical_bottlenecks():
    _assert_equal(
        {"R1": (0.5, 0.5)}, [_bn(0, 0, severity="MEDIUM")], 1000.0, 5, 5
    )


def test_violations_severity_reads_last_bottleneck():
    """The VERBATIM quirk: violation severity == the LAST bottleneck's
    severity (the first loop's `bn` stays bound), NOT the matched cell's."""
    bottlenecks = [_bn(0, 0, layer="F.Cu", severity="CRITICAL"), _bn(0, 0, layer="B.Cu", severity="MEDIUM", score=0.5)]
    got = RS_VIOL({"R1": (0.5, 0.5)}, _flat(bottlenecks), 1000.0, 5, 5)
    exp = _oracle.find_critical_bottleneck_violations(
        {"R1": (0.5, 0.5)}, bottlenecks, 1000.0, 5, 5
    )
    assert canon(got) == canon(exp)
    assert got[0]["severity"] == "MEDIUM"  # last bottleneck, not "CRITICAL"


def test_violations_score_tie_first_wins():
    # Equal scores -> FIRST bottleneck kept in critical_by_cell -> its layer.
    bottlenecks = [_bn(0, 0, layer="F.Cu", score=0.8), _bn(0, 0, layer="B.Cu", score=0.8)]
    _assert_equal({"R1": (0.5, 0.5)}, bottlenecks, 1000.0, 5, 5)


def test_violations_higher_score_wins_layer():
    bottlenecks = [_bn(0, 0, layer="F.Cu", score=0.6), _bn(0, 0, layer="B.Cu", score=0.9)]
    got = RS_VIOL({"R1": (0.5, 0.5)}, _flat(bottlenecks), 1000.0, 5, 5)
    assert got[0]["layer"] == "B.Cu"
    assert got[0]["severity"] == "CRITICAL"


def test_violations_floor_negative_coordinates():
    """-0.001mm lands at gx = -1 (floor toward -inf) -> out of grid -> skipped.
    Exactly 0.0 lands at gx = 0."""
    _assert_equal({"R1": (-0.001, 0.0)}, [_bn(0, 0)], 1000.0, 5, 5)
    _assert_equal({"R1": (0.0, 0.0)}, [_bn(0, 0)], 1000.0, 5, 5)
    _assert_equal({"R1": (0.9999, 0.9999)}, [_bn(0, 0)], 1000.0, 5, 5)


def test_violations_out_of_grid_skipped():
    _assert_equal({"R1": (5.0, 5.0)}, [_bn(5, 5)], 1000.0, 5, 5)
    _assert_equal({"R1": (-1.0, 0.0)}, [_bn(0, 0)], 1000.0, 5, 5)
    _assert_equal({"R1": (0.0, 6.0)}, [_bn(0, 0)], 1000.0, 5, 5)


def test_violations_non_tuple_positions_skipped():
    _assert_equal({"R1": (0.5,)}, [_bn(0, 0)], 1000.0, 5, 5)
    _assert_equal({"R1": 3.14}, [_bn(0, 0)], 1000.0, 5, 5)
    _assert_equal({"R1": None}, [_bn(0, 0)], 1000.0, 5, 5)


def test_violations_int_coordinates():
    _assert_equal({"R1": (0, 0)}, [_bn(0, 0)], 1000.0, 5, 5)


def test_violations_expression_order_float_coercion():
    """float(x_mm) * 1000.0 / cell_um computed in that order (a Rust that
    computes x_mm / (cell_um / 1000.0) diverges in the last ulp)."""
    _assert_equal({"R1": (0.3, 0.7)}, [_bn(3, 7)], 100.0, 20, 20)


def test_violations_multiple_placements_order_preserved():
    placements = {"R1": (0.5, 0.5), "R2": (1.5, 1.5), "R3": (3.5, 3.5)}
    bottlenecks = [
        _bn(0, 0, layer="F.Cu"),
        _bn(1, 1, layer="B.Cu", score=0.5),
    ]
    got = RS_VIOL(placements, _flat(bottlenecks), 1000.0, 5, 5)
    assert [v["ref"] for v in got] == ["R1", "R2"]


def test_violations_empty_inputs():
    _assert_equal({}, [_bn(0, 0)], 1000.0, 5, 5)
    _assert_equal({"R1": (0.5, 0.5)}, [], 1000.0, 5, 5)
    _assert_equal({}, [], 1000.0, 5, 5)


def test_violations_randomized():
    rng = random.Random(3)
    for _ in range(150):
        cell_um = rng.choice([100.0, 250.0, 500.0, 1000.0, 2540.0])
        width, height = rng.randint(2, 30), rng.randint(2, 30)
        bottlenecks = []
        for _ in range(rng.randint(0, 8)):
            x = rng.randint(-2, width + 2)
            y = rng.randint(-2, height + 2)
            sev = rng.choice(["CRITICAL", "HIGH", "MEDIUM", "LOW", "CRITICAL"])
            bottlenecks.append(_bn(x, y, layer=rng.choice(["F.Cu", "B.Cu"]), severity=sev, score=round(rng.uniform(0, 1), 4)))
        placements = {}
        for i in range(rng.randint(0, 6)):
            x_mm = rng.uniform(-2.0, width * cell_um / 1000.0 + 2.0)
            y_mm = rng.uniform(-2.0, height * cell_um / 1000.0 + 2.0)
            placements[f"C{i}"] = (x_mm, y_mm)
        _assert_equal(placements, bottlenecks, cell_um, width, height)


def test_violations_non_vacuity_guard():
    """The kernel must actually flag a critical cell, not return [] always."""
    got = RS_VIOL({"R1": (0.5, 0.5)}, [(0, 0, "F.Cu", "CRITICAL", 1.0)], 1000.0, 5, 5)
    assert got == [{"ref": "R1", "x": 0, "y": 0, "layer": "F.Cu", "severity": "CRITICAL"}]
