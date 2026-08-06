"""Differential tests: DRC-check deterministic leaf kernels, Rust vs oracle.

Wave 4, Phase 5, batch 2 (deterministic leaf stages). The pure compute of
``drc_validation.py`` / ``drc_sweep.py`` (TrackDeduplicationStage) /
``placement_validation.py`` / ``courtyard_check.py`` moves to the
``temper-drc-rs`` crate; the Python modules become delegation shims. The
pre-migration implementations are pinned VERBATIM as the oracle
(``_drc_leaf_py_oracle.py``).

R1a: violation summarization (descending-count order, first-seen tie
order), the dedup key (`round(x/tol) * tol` half-to-even, direction
normalisation, net/layer in the key), the point-to-segment distance (libm
pow/sqrt bit-exact), the two constraint validators (messages via CPython
`__format__`), and the clamp compare bit-identically.
"""

from __future__ import annotations

import temper_drc_rs as _drc
import tests.deterministic.stages._drc_leaf_py_oracle as _oracle
from tests.core._contract_canon import canon


class _V:
    def __init__(self, vtype):
        self.type = vtype


class _Constraint:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def test_summarize_violations_counts():
    vs = [_V("a"), _V("b"), _V("a"), _V("c"), _V("a")]
    total, rows = _drc.summarize_violations_py(vs)
    assert total == 5
    assert rows == [("a", 3), ("b", 1), ("c", 1)]
    # Order is descending count, ties in first-seen order.
    total2, rows2 = _drc.summarize_violations_py([_V("x"), _V("y")])
    assert rows2 == [("x", 1), ("y", 1)]


def test_summarize_violations_empty():
    total, rows = _drc.summarize_violations_py([])
    assert total == 0 and rows == []


def test_threshold_decision():
    assert _oracle.threshold_decision(True, 0, 1) == (True, "1 DRC violations found")
    assert _oracle.threshold_decision(True, 0, 0) == (False, "")
    assert _oracle.threshold_decision(False, 3, 4) == (True, "4 violations exceeds max 3")
    assert _oracle.threshold_decision(False, 3, 3) == (False, "")  # strict >
    assert _oracle.threshold_decision(False, 3, 2) == (False, "")


def test_dedup_basic():
    traces = [
        ((0.0, 0.0), (10.0, 0.0), 0, "A"),
        ((10.0, 0.0), (0.0, 0.0), 0, "A"),  # reversed duplicate
        ((0.0, 0.0), (10.0, 0.0), 0, "B"),  # different net
    ]
    exp = _oracle.deduplicate_traces(traces, 0.05)
    got = _drc.deduplicate_traces_py(traces, 0.05)
    assert got == exp == ([0, 2], 1)


def test_dedup_tolerance_rounding():
    """round(x/tol)*tol: within-half slots collapse, exact halves half-even."""
    traces = [
        ((0.0, 0.0), (10.0, 0.0), 0, "A"),
        ((0.025, 0.0), (10.0, 0.0), 0, "A"),  # 0.025/0.05 = 0.5 -> round 0 (dedup)
        ((0.049, 0.0), (10.0, 0.0), 0, "A"),  # 0.98 -> round 1 -> key 0.05 (kept)
    ]
    exp = _oracle.deduplicate_traces(traces, 0.05)
    got = _drc.deduplicate_traces_py(traces, 0.05)
    assert got == exp
    assert got == ([0, 2], 1)


def test_dedup_float_bits():
    """Non-representable coords pin the rounded-key bits."""
    traces = [
        ((0.1, 0.2), (10.3, 0.4), 0, "N"),
        ((0.1000001, 0.2000001), (10.3, 0.4), 0, "N"),
        ((0.1, 0.2), (10.3, 0.4), 1, "N"),  # different layer
    ]
    exp = _oracle.deduplicate_traces(traces, 0.05)
    got = _drc.deduplicate_traces_py(traces, 0.05)
    assert got == exp


def test_dedup_net_none():
    traces = [((0.0, 0.0), (1.0, 0.0), 0, None), ((1.0, 0.0), (0.0, 0.0), 0, None)]
    exp = _oracle.deduplicate_traces(traces, 0.05)
    got = _drc.deduplicate_traces_py(traces, 0.05)
    assert got == exp == ([0], 1)


def _assert_pts2seg(point, start, end):
    exp = _oracle.point_to_segment_distance(point, start, end)
    got = _drc.point_to_segment_distance_py(point, start, end)
    assert got.hex() == exp.hex(), f"{point} {start} {end}"


def test_pts2seg_basic():
    _assert_pts2seg((2.0, 3.0), (0.0, 0.0), (4.0, 0.0))
    _assert_pts2seg((0.0, 0.0), (0.0, 0.0), (4.0, 0.0))
    _assert_pts2seg((6.0, 3.0), (0.0, 0.0), (4.0, 0.0))
    _assert_pts2seg((2.0, 3.0), (0.0, 0.0), (0.0, 0.0))  # degenerate segment


def test_pts2seg_float_bits():
    _assert_pts2seg((0.1, 0.2), (0.3, 0.4), (0.7, 0.9))
    _assert_pts2seg((-1.5, 2.5), (-0.3, 0.2), (1.1, -0.7))


def test_pts2seg_off_segment_negative_t():
    _assert_pts2seg((-5.0, 3.0), (0.0, 0.0), (4.0, 0.0))


def _positions(mapping):
    return dict(mapping)


def _prox_constraint(**kw):
    defaults = dict(
        name="P1", from_component="Q1", from_pin="1", to_component="Q2", to_pin="2",
        max_distance_mm=15.0, tier="hard",
    )
    defaults.update(kw)
    return _Constraint(**defaults)


def _prox_result_to_canon(result):
    if result is None:
        return None
    return {
        "type": result[0], "severity": result[1], "actual": result[2], "required": result[3],
        "message": result[4], "comp_a": result[5], "comp_b": result[6],
    }


def test_proximity_no_violation():
    c = _prox_constraint()
    exp = _oracle.validate_proximity(c, {"Q1": (0.0, 0.0), "Q2": (5.0, 5.0)})
    got = _drc.validate_proximity_py(c, (0.0, 0.0), (5.0, 5.0))
    assert got is not None and got[0] is False
    assert exp is None


def test_proximity_violation():
    c = _prox_constraint(max_distance_mm=3.0)
    exp = _oracle.validate_proximity(c, {"Q1": (0.0, 0.0), "Q2": (10.0, 0.0)})
    got = _drc.validate_proximity_py(c, (0.0, 0.0), (10.0, 0.0))
    assert got is not None and got[0] is True
    assert got[1] == "error"
    assert got[2].hex() == exp["actual_distance_mm"].hex()
    assert got[4] == exp["message"]


def test_proximity_missing_component():
    c = _prox_constraint()
    exp = _oracle.validate_proximity(c, {"Q1": (0.0, 0.0)})
    got = _drc.validate_proximity_py(c, (0.0, 0.0), None)
    assert got[0] is True and got[1] == "warning"
    assert got[4] == exp["message"] == "Cannot validate P1: component not found"


def test_proximity_soft_tier():
    c = _prox_constraint(max_distance_mm=3.0, tier="soft")
    got = _drc.validate_proximity_py(c, (0.0, 0.0), (10.0, 0.0))
    assert got[1] == "warning"


def test_signal_hv_path_too_long():
    c = _Constraint(
        name="S1", signal_component="U1", signal_pin="1", target_component="U2",
        target_pin="2", hv_component="Q1", hv_pins=["3"], required_clearance_mm=6.0,
        max_path_length_mm=10.0, tier="hard",
    )
    exp = _oracle.validate_signal_hv(c, {"U1": (0.0, 0.0), "U2": (50.0, 0.0), "Q1": (25.0, 1.0)})
    got = _drc.validate_signal_hv_py(c, (0.0, 0.0), (50.0, 0.0), [("3", (25.0, 1.0))])
    assert got is not None and got[0] is True
    assert got[1] == "error"
    assert got[4] == exp["message"]
    assert "path_too_long" not in got[4]


def test_signal_hv_clearance_violation():
    c = _Constraint(
        name="S2", signal_component="U1", signal_pin="1", target_component="U2",
        target_pin="2", hv_component="Q1", hv_pins=["3"], required_clearance_mm=6.0,
        max_path_length_mm=50.0, tier="hard",
    )
    exp = _oracle.validate_signal_hv(c, {"U1": (0.0, 0.0), "U2": (50.0, 0.0), "Q1": (25.0, 0.5)})
    got = _drc.validate_signal_hv_py(c, (0.0, 0.0), (50.0, 0.0), [("3", (25.0, 0.5))])
    assert got is not None and got[0] is True
    assert got[4] == exp["message"]
    assert got[2].hex() == exp["actual_distance_mm"].hex()


def test_signal_hv_clean():
    c = _Constraint(
        name="S3", signal_component="U1", signal_pin="1", target_component="U2",
        target_pin="2", hv_component="Q1", hv_pins=["3"], required_clearance_mm=6.0,
        max_path_length_mm=50.0, tier="hard",
    )
    exp = _oracle.validate_signal_hv(c, {"U1": (0.0, 0.0), "U2": (50.0, 0.0), "Q1": (25.0, 30.0)})
    got = _drc.validate_signal_hv_py(c, (0.0, 0.0), (50.0, 0.0), [("3", (25.0, 30.0))])
    assert got is not None and got[0] is False
    assert exp is None


def test_signal_hv_missing_target():
    c = _Constraint(
        name="S4", signal_component="U1", signal_pin="1", target_component="MISSING",
        target_pin="2", hv_component="Q1", hv_pins=["3"], required_clearance_mm=6.0,
        max_path_length_mm=50.0, tier="hard",
    )
    exp = _oracle.validate_signal_hv(c, {"U1": (0.0, 0.0), "Q1": (25.0, 30.0)})
    got = _drc.validate_signal_hv_py(c, (0.0, 0.0), None, [("3", (25.0, 30.0))])
    assert got[0] is True and got[1] == "warning"
    assert got[4] == exp["message"]


def _assert_clamp(pos, margin, w, h):
    exp = _oracle.clamp_position(pos, margin, w, h)
    got = _drc.clamp_position_py(pos[0], pos[1], margin, w, h)
    assert got == exp


def test_clamp_position():
    _assert_clamp((50.0, 75.0), 5.0, 100.0, 150.0)
    _assert_clamp((-10.0, 200.0), 5.0, 100.0, 150.0)
    _assert_clamp((0.0, 0.0), 5.0, 100.0, 150.0)
    _assert_clamp((95.0, 145.0), 5.0, 100.0, 150.0)
    _assert_clamp((200.0, -5.0), 5.0, 100.0, 150.0)
