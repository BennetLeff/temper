"""R1a: behavioural A/B of the pipeline-feasibility Rust port against the
pinned oracle.

Wave 4, pipeline slice: the feasibility/check compute of
``temper_placer.pipeline.{convergence,preflight,derivation}`` moves to the
``temper-orchestration`` crate (``temper_orchestration.record_loss`` /
``check_success`` / ``is_converged`` / ``check_routability_regression`` /
``component_area_ratio`` / ``proximity_rule_impossible`` /
``zone_over_capacity`` / ``loop_area_violation`` /
``isolation_barrier_too_large`` / ``builtin_sum`` / ``derive_emi_max_dist`` /
``derive_thermal_clearance`` / ``derive_si_max_placement_dist`` /
``mains_voltage_to_class_code`` / ``extract_min_clearance``). The Python
modules keep their full public API (dataclasses, enums, the
``ConvergenceChecker``/``PreflightChecker`` classes and the module-level
functions) and delegate the compute across the boundary.

The pre-migration modules are pinned VERBATIM as the oracle
(``tests/pipeline/_pipeline_feasibility_py_oracle.py``). Both arms are driven
with IDENTICAL inputs; every assertion is bit-exact.

Bit-exactness conventions (R1a):
- floats compare via ``float.hex()`` (canon) — never a tolerance;
- every leaf carries its concrete ``type`` (``int`` vs ``float`` cannot hide);
- error parity via ``canon_call``.

Numerical traps pinned here:
- ``sum(...)`` over floats is CPython 3.12's improved Kahan-Babuska
  (Neumaier) compensated algorithm (catalog class B12) — NOT naive addition.
  The preflight keepout-area sum mixes int ``0`` entries with float products;
  in CPython's ``builtin_sum_impl`` (v3.12.13, bltinmodule.c) those hit the
  float fast path's ``f_result += (double)value`` no-op branch, so the mixed
  sequence sums exactly like the float products alone, in order — the
  module-level ``PreflightChecker.run`` differential pins this with a
  real mixed-length keepout list, and ``builtin_sum`` is pinned directly
  against the builtin.
- CPython ``min(a, b)`` is first-argument-kept: asymmetric on NaN and ties
  (catalog B5-adjacent) — the proximity and isolation kernels replicate it.
- ``check_routability_regression`` is a stateful decision over net-set
  identity; the module-level differential drives both arms through an
  identical call sequence and compares every per-call return, every state
  snapshot and every rendered ``failure_message``.
- ``record_loss``'s ``(best_loss - loss) / best_loss`` improvement ratio and
  the first-loss ``best_loss == inf`` branch are pinned bit-exactly.
"""

from __future__ import annotations

import hashlib
import math
import random
from pathlib import Path
from types import SimpleNamespace

import pytest
import temper_orchestration as _to

from temper_placer.pipeline import convergence as _conv
from temper_placer.pipeline import derivation as _der
from temper_placer.pipeline import preflight as _pref
from tests.core._contract_canon import canon, canon_call
from tests.pipeline import _pipeline_feasibility_py_oracle as _oracle

# --- Rust symbols under test ---
RS_RECORD_LOSS = _to.record_loss
RS_CHECK_SUCCESS = _to.check_success
RS_IS_CONVERGED = _to.is_converged
RS_CHECK_ROUTABILITY_REGRESSION = _to.check_routability_regression
RS_COMPONENT_AREA_RATIO = _to.component_area_ratio
RS_PROXIMITY_RULE = _to.proximity_rule_impossible
RS_ZONE_OVER_CAPACITY = _to.zone_over_capacity
RS_LOOP_AREA_VIOLATION = _to.loop_area_violation
RS_ISOLATION_BARRIER = _to.isolation_barrier_too_large
RS_BUILTIN_SUM = _to.builtin_sum
RS_DERIVE_EMI = _to.derive_emi_max_dist
RS_DERIVE_THERMAL = _to.derive_thermal_clearance
RS_DERIVE_SI = _to.derive_si_max_placement_dist
RS_MAINS_CLASS = _to.mains_voltage_to_class_code
RS_EXTRACT_MIN_CLEARANCE = _to.extract_min_clearance


# ---------------------------------------------------------------------------
# The oracle must stay verbatim
# ---------------------------------------------------------------------------

_ORACLE_PATH = Path(__file__).with_name("_pipeline_feasibility_py_oracle.py")
_PINNED_BODY_SHA256 = "296cac0c6dd601a8f544996fdd85283cc6c8c95cbb131e169d0d13438f613487"
_BODY_MARKER = "# --- BEGIN PINNED BODY ---\n"


def test_oracle_body_matches_pinned_digest() -> None:
    """The oracle is evidence only while it is unmodified.

    A differential whose oracle can be edited to agree with the port proves
    nothing, so the copied body is content-addressed. If this fails, either
    the oracle was edited (revert it) or a pre-migration module's source
    really changed upstream (re-pin deliberately, in its own commit).
    """
    text = _ORACLE_PATH.read_text(encoding="utf-8")
    assert _BODY_MARKER in text, "oracle header marker missing"
    body = text.split(_BODY_MARKER, 1)[1]
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    assert digest == _PINNED_BODY_SHA256, (
        "the pinned oracle body changed; it must stay verbatim "
        f"(expected {_PINNED_BODY_SHA256}, got {digest})"
    )


def test_oracle_and_port_are_different_implementations() -> None:
    """Anti-vacuity: guard against both arms being the same object."""
    assert _conv is not _oracle
    assert _conv.ConvergenceChecker is not _oracle.ConvergenceChecker
    assert _conv.is_converged is not _oracle.is_converged
    assert _pref.PreflightChecker is not _oracle.PreflightChecker
    assert _der.derive_constraints_from_spec is not _oracle.derive_constraints_from_spec
    # The ports must actually be routed through Rust.
    assert hasattr(_conv, "_rs")
    assert hasattr(_pref, "_rs")
    assert hasattr(_der, "_rs")
    assert hasattr(_conv._rs, "check_routability_regression")
    assert hasattr(_pref._rs, "component_area_ratio")
    assert hasattr(_der._rs, "mains_voltage_to_class_code")


# ---------------------------------------------------------------------------
# Reference arms — mechanically extracted from the oracle's bodies.
# ---------------------------------------------------------------------------


def _ref_record_loss(best_loss, loss, min_improvement):
    """Extracted from ConvergenceChecker.record_loss (oracle body)."""
    if best_loss == float("inf"):
        return (loss, True)
    improvement = (best_loss - loss) / best_loss
    if improvement >= min_improvement:
        return (loss, True)
    return (best_loss, False)


def _ref_check_success(overlap, boundary, routing, margin,
                       max_overlap, max_boundary, min_routing, min_margin):
    """Extracted from ConvergenceChecker.check_success (oracle body)."""
    if overlap > max_overlap:
        return False
    if boundary > max_boundary:
        return False
    if routing < min_routing:
        return False
    if margin < min_margin:  # noqa: SIM103 - verbatim oracle shape
        return False
    return True


def _ref_is_converged(current, previous):
    """Extracted from is_converged (oracle body); pairs are (success, length)."""
    if not current:
        return False
    all_success = all(s for s, _ in current)
    if all_success:
        return True
    if previous is None:
        return False
    curr_len = sum(length for _, length in current)
    prev_len = sum(length for _, length in previous)
    curr_succ = sum(1 for s, _ in current if s)
    prev_succ = sum(1 for s, _ in previous if s)
    return bool(curr_succ == prev_succ and abs(curr_len - prev_len) < 1e-06)


def _ref_component_area_ratio(dims, board_width, board_height, keepout_dims):
    """Extracted from _check_component_area (oracle body). code: 0=PASS,
    1=WARN, 2=FAIL."""
    total_area = sum(w * h for w, h in dims)
    board_area = board_width * board_height
    keepout_area = sum(w * h for w, h in keepout_dims)
    usable_area = board_area - keepout_area
    ratio = total_area / usable_area if usable_area > 0 else 1.0
    code = 2 if ratio > 0.85 else (1 if ratio > 0.7 else 0)
    return (ratio, code)


def _ref_proximity_rule(wa, ha, wb, hb, max_d):
    """Extracted from _check_constraint_satisfiability (oracle body)."""
    min_d = min((wa + wb) / 2.0, (ha + hb) / 2.0)
    return (min_d, max_d < min_d)


def _ref_zone_over_capacity(w, h, dims):
    """Extracted from _check_zone_capacity (oracle body)."""
    cap = w * h
    content = sum(cw * ch for cw, ch in dims)
    return content > cap * 0.9


def _ref_loop_area_violation(max_a, truthy, dims):
    """Extracted from _check_loop_area_feasibility (oracle body)."""
    total_a = sum(cw * ch for cw, ch in dims)
    return bool(truthy and max_a < total_a * 0.5)


def _ref_isolation_barrier(dims, board_width, board_height, iso):
    """Extracted from _check_isolation_feasibility (oracle body)."""
    barrier_a = min(board_width, board_height) * iso
    total_a = sum(cw * ch for cw, ch in dims)
    return total_a + barrier_a > board_width * board_height * 0.95


def _ref_derive_emi(area):
    """Extracted from derive_constraints_from_spec EMI block (oracle body)."""
    return math.sqrt(area) * 0.8


def _ref_derive_thermal(power):
    """Extracted from derive_constraints_from_spec thermal block."""
    return power * 2.0


def _ref_derive_si(max_len):
    """Extracted from derive_constraints_from_spec SI block."""
    return max_len / 1.5


def _ref_mains_voltage_class(v):
    """Extracted from _mains_voltage_to_class (oracle body) as a code."""
    if v <= 50:
        return 0
    elif v <= 130:
        return 1
    elif v <= 264:
        return 2
    else:
        return 3


def _ref_extract_min_clearance(key, value):
    """Extracted from apply_derived_constraints (oracle body)."""
    if key.endswith("_min_clearance"):
        return (key.replace("_min_clearance", ""), value)
    return None


# ---------------------------------------------------------------------------
# convergence kernels
# ---------------------------------------------------------------------------


def _assert_record_loss(best, loss, min_imp):
    # canon_call: the zero-best case must raise ZeroDivisionError in BOTH
    # arms (Python division vs the kernel's explicit raise), with parity.
    ref = canon_call(_ref_record_loss, best, loss, min_imp)
    got = canon_call(RS_RECORD_LOSS, best, loss, min_imp)
    assert ref == got, f"record_loss mismatch: best={best!r} loss={loss!r} min={min_imp!r}\n  ref={ref}\n  got={got}"


@pytest.mark.parametrize(
    "best,loss,min_imp",
    [
        (float("inf"), 100.0, 0.001),
        (float("inf"), float("nan"), 0.001),
        (100.0, 90.0, 0.01),
        (100.0, 99.5, 0.01),
        (100.0, 100.0, 0.01),
        (100.0, 0.0, 0.01),
        (100.0, float("nan"), 0.001),
        (0.0, -10.0, 0.01),
        (-100.0, -110.0, 0.01),
        (1e-300, 9e-301, 0.01),
        (1e300, 9e299, 0.01),
        (float("-inf"), 1.0, 0.01),
        (50.0, 49.999, 0.001),
    ],
    ids=lambda c: repr(c),
)
def test_record_loss_bit_exact(best, loss, min_imp):
    _assert_record_loss(best, loss, min_imp)


def _assert_check_success(args):
    ref = canon(_ref_check_success(*args))
    got = canon(RS_CHECK_SUCCESS(*args))
    assert ref == got, f"check_success mismatch: {args}\n  ref={ref}\n  got={got}"


def _check_success_cases():
    base = (0.0, 0.0, 1.0, 0.1, 0.01, 0.01, 1.0, 0.05)
    cases = [base]
    # one metric beyond each threshold
    cases.append((0.02, 0.0, 1.0, 0.1, 0.01, 0.01, 1.0, 0.05))
    cases.append((0.0, 0.02, 1.0, 0.1, 0.01, 0.01, 1.0, 0.05))
    cases.append((0.0, 0.0, 0.99, 0.1, 0.01, 0.01, 1.0, 0.05))
    cases.append((0.0, 0.0, 1.0, 0.049, 0.01, 0.01, 1.0, 0.05))
    # defaults: inf overlap/boundary fail, missing routing/margin default 0.0
    cases.append((float("inf"), 0.0, 1.0, 0.1, 0.01, 0.01, 1.0, 0.05))
    cases.append((0.0, float("inf"), 1.0, 0.1, 0.01, 0.01, 1.0, 0.05))
    cases.append((0.0, 0.0, 0.0, 0.0, 0.01, 0.01, 1.0, 0.05))
    # NaN never fails a comparison (NaN > x / NaN < x are both False)
    cases.append((float("nan"), 0.0, 1.0, 0.1, 0.01, 0.01, 1.0, 0.05))
    cases.append((0.0, float("nan"), 1.0, 0.1, 0.01, 0.01, 1.0, 0.05))
    cases.append((0.0, 0.0, float("nan"), 0.1, 0.01, 0.01, 1.0, 0.05))
    cases.append((0.0, 0.0, 1.0, float("nan"), 0.01, 0.01, 1.0, 0.05))
    # exact-boundary ties: equal is not greater/less
    cases.append((0.01, 0.0, 1.0, 0.05, 0.01, 0.01, 1.0, 0.05))
    cases.append((0.0, 0.0, 1.0, 0.05, 0.01, 0.01, 1.0, 0.05))
    cases.append((0.0, 0.0, 1.0, 0.1, 0.01, 0.01, 1.0, 0.05))
    return cases


@pytest.mark.parametrize("args", _check_success_cases(), ids=repr)
def test_check_success_bit_exact(args):
    _assert_check_success(args)


def _assert_is_converged(current, previous):
    ref = canon(_ref_is_converged(current, previous))
    got = canon(RS_IS_CONVERGED(current, previous))
    assert ref == got, (
        f"is_converged mismatch: current={current!r} previous={previous!r}\n"
        f"  ref={ref}\n  got={got}"
    )


@pytest.mark.parametrize(
    "current,previous",
    [
        ([], None),
        ([], []),
        ([(True, 100.0), (True, 200.0)], None),
        ([(True, 100.0), (False, 200.0)], None),
        ([(False, 100.0), (False, 200.0)], None),
        ([(False, 100.0), (False, 200.0)], [(False, 100.0), (False, 200.0)]),
        ([(False, 100.0), (False, 200.0)], [(False, 150.0), (False, 200.0)]),
        ([(False, 100.0), (False, 200.0)], [(True, 100.0), (False, 200.0)]),
        ([(False, 100.0), (False, 200.0)], [(False, 100.0), (True, 200.0)]),
        ([(False, 1.0e16), (False, 1.0)], [(False, 1.0e16), (False, 0.0)]),
        ([(False, float("nan"))], [(False, float("nan"))]),
        ([(False, 1e-6)], [(False, 0.0)]),
        ([(False, 1.000001)], [(False, 1.0)]),
    ],
    ids=repr,
)
def test_is_converged_bit_exact(current, previous):
    _assert_is_converged(current, previous)


def test_builtin_sum_matches_python_sum() -> None:
    """B12 direct pin: the compensated helper vs the builtin sum()."""
    rng = random.Random(20260809)
    values = [[rng.uniform(-1e6, 1e6) for _ in range(rng.randint(0, 12))] for _ in range(40)]
    values += [
        [],
        [3.5],
        [-0.0],
        [-0.0, -0.0],
        [1e16, 1.0, -1e16],
        [1e308, 1e308, -1e308],
    ]
    for vs in values:
        ref = canon(sum(vs))
        got = canon(RS_BUILTIN_SUM(vs))
        assert ref == got, f"builtin_sum mismatch for {vs!r}\n  ref={ref}\n  got={got}"
    # single-element negative zero: CPython seeds `0 + (-0.0)` = +0.0
    assert RS_BUILTIN_SUM([-0.0]).hex() == sum([-0.0]).hex() == (0.0).hex()


# ---------------------------------------------------------------------------
# convergence module-level differentials (the delegation shims)
# ---------------------------------------------------------------------------


def _new_checkers(criteria_kwargs: dict):
    py_criteria = _oracle.ConvergenceCriteria(**criteria_kwargs)
    rs_criteria = _conv.ConvergenceCriteria(**criteria_kwargs)
    py_checker = _oracle.ConvergenceChecker(py_criteria)
    rs_checker = _conv.ConvergenceChecker(rs_criteria)
    # The routability-regression state attributes are created lazily; every
    # real caller pre-initializes them (see test_convergence.py), and both
    # arms raise AttributeError on a truly fresh state — so the differential
    # pre-initializes exactly like the callers.
    for checker in (py_checker, rs_checker):
        checker.state._best_routed_nets = None
        checker.state._best_routability = None
        checker.state._stall_count = 0
    return py_checker, rs_checker


def _convergence_state_snapshot(checker) -> dict:
    s = checker.state
    return {
        "iteration": s.iteration,
        "loss_history": [canon(x) for x in s.loss_history],
        "best_loss": canon(s.best_loss),
        "epochs_since_improvement": s.epochs_since_improvement,
        "terminated": s.terminated,
        "reason": s.termination_reason.value if s.termination_reason is not None else None,
        "message": s.failure_message,
        # _best_routed_nets / _best_routability / _stall_count are created
        # lazily by the first check_routability_regression call.
        "best_routed": (
            sorted(s._best_routed_nets)
            if getattr(s, "_best_routed_nets", None) is not None
            else None
        ),
        "best_ratio": canon(getattr(s, "_best_routability", None)),
        "stall": getattr(s, "_stall_count", 0),
    }


def test_convergence_checker_record_loss_sequence() -> None:
    py_checker, rs_checker = _new_checkers({"min_loss_improvement": 0.01})
    losses = [100.0, 90.0, 99.5, 89.0, 89.0, 88.0, 100.0, float("nan")]
    for loss in losses:
        py_checker.record_loss(loss)
        rs_checker.record_loss(loss)
        assert _convergence_state_snapshot(py_checker) == _convergence_state_snapshot(
            rs_checker
        ), f"record_loss state diverged after {loss!r}"
    assert rs_checker.state.best_loss == 88.0
    assert rs_checker.state.epochs_since_improvement == 2


def test_convergence_checker_check_success_metrics_defaults() -> None:
    py_checker, rs_checker = _new_checkers({})
    metric_sets = [
        {"overlap_mm2": 0.0, "boundary_violation_mm": 0.0,
         "routing_completion": 1.0, "manufacturing_margin_mm": 0.1},
        {"overlap_mm2": 1.0},
        {"routing_completion": 0.5},
        {"overlap_mm2": 0.0, "boundary_violation_mm": 0.0,
         "routing_completion": 1.0, "manufacturing_margin_mm": 0.0},
        {},
        {"overlap_mm2": float("nan")},
    ]
    for metrics in metric_sets:
        py_res = py_checker.check_success(metrics)
        rs_res = rs_checker.check_success(metrics)
        assert py_res == rs_res, f"check_success diverged for {metrics!r}"
        assert _convergence_state_snapshot(py_checker) == _convergence_state_snapshot(
            rs_checker
        )


_ROUTABILITY_SEQUENCE = [
    # (routed, total, previous, threshold, stall_limit)
    ({"N1", "N2", "N3"}, 10, None, 0.95, 2),          # seed: best 0.3
    ({"N1", "N2", "N3", "N4"}, 10, {"N1", "N2", "N3"}, 0.95, 2),   # improve 0.4
    ({"N1", "N2", "N3", "N4"}, 10, {"N1", "N2", "N3", "N4"}, 0.95, 2),  # stall 1
    ({"N1", "N2", "N3", "N4"}, 10, {"N1", "N2", "N3", "N4"}, 0.95, 2),  # stall 2 -> converged
    ({"N1"}, 10, {"N1"}, 0.5, 2),                     # regression: 0.1 < 0.4*0.5
    ({"N1", "N2"}, 10, None, 0.95, 2),                # 0.2 < 0.4*0.95 -> regression
    ({"N1", "N2", "N3", "N4", "N5", "N6"}, 10, None, 0.95, 2),  # 0.6 > 0.38 -> improve
    ({"N1", "N2", "N3", "N4", "N5", "N6"}, 10, {"N1", "N2", "N3", "N4", "N5", "N6"}, 0.95, 3),  # stall 1
    ({"N1", "N2", "N3", "N4", "N5", "N6"}, 10, {"N1", "N2", "N3", "N4", "N5", "N6"}, 0.95, 3),  # stall 2
    ({"N1", "N2", "N3", "N4", "N5", "N6"}, 10, {"N1", "N2", "N3", "N4", "N5", "N6"}, 0.95, 3),  # stall 3 -> converged
    (set(), 10, None, 0.95, 2),                       # empty routed, ratio 0.0
    ({"A"}, 0, None, 0.95, 2),                        # total_nets 0 -> max(0,1)=1
    ({"N1", "N2", "N3", "N4", "N5", "N6"}, 10, None, 0.95, 2),  # 0.6 == best, no change
]


def test_check_routability_regression_sequence_bit_exact() -> None:
    """Both arms agree on every return value, state snapshot and rendered
    failure message across a stateful sequence covering seed / improvement /
    stall / convergence / regression / empty / zero-total."""
    py_checker, rs_checker = _new_checkers({})
    for routed, total, prev, thr, stall in _ROUTABILITY_SEQUENCE:
        prev_arg = frozenset(prev) if prev is not None else None
        py_res = py_checker.check_routability_regression(
            frozenset(routed), total, prev_arg, thr, stall
        )
        rs_res = rs_checker.check_routability_regression(
            frozenset(routed), total, prev_arg, thr, stall
        )
        assert py_res == rs_res, (
            f"return diverged for routed={sorted(routed)} total={total} prev={prev} "
            f"thr={thr} stall={stall}: py={py_res} rs={rs_res}"
        )
        py_snap = _convergence_state_snapshot(py_checker)
        rs_snap = _convergence_state_snapshot(rs_checker)
        assert py_snap == rs_snap, (
            f"state diverged after routed={sorted(routed)} total={total} prev={prev}\n"
            f"  py={py_snap}\n  rs={rs_snap}"
        )


def _routability_result(checker, routed, total, prev, thr, stall):
    return checker.check_routability_regression(
        frozenset(routed), total,
        frozenset(prev) if prev is not None else None,
        thr, stall,
    )


def test_check_routability_regression_messages() -> None:
    """Pin the rendered failure messages on both arms (formatting parity)."""
    # Scenario 1: regression with lost nets.
    py_checker, rs_checker = _new_checkers({})
    for checker in (py_checker, rs_checker):
        _routability_result(checker, {"N1", "N2", "N3", "N4", "N5"}, 10, None, 0.95, 2)
    py_msg = _routability_result(py_checker, {"N1", "N2"}, 10, None, 0.5, 2)
    rs_msg = _routability_result(rs_checker, {"N1", "N2"}, 10, None, 0.5, 2)
    assert py_msg is True and rs_msg is True
    assert py_checker.state.failure_message == rs_checker.state.failure_message
    assert "Routability regressed: 0.200 < 0.250 (threshold)." in (
        rs_checker.state.failure_message
    )
    assert "Lost nets: ['N3', 'N4', 'N5']" in rs_checker.state.failure_message

    # Scenario 2: regression with no lost nets (routed == best but ratio
    # below threshold * 1.5).
    py_checker, rs_checker = _new_checkers({})
    for checker in (py_checker, rs_checker):
        _routability_result(checker, {"N1", "N2"}, 10, None, 0.95, 2)
    py_msg = _routability_result(py_checker, {"N1", "N2"}, 10, None, 1.5, 2)
    rs_msg = _routability_result(rs_checker, {"N1", "N2"}, 10, None, 1.5, 2)
    assert py_msg is True and rs_msg is True
    assert py_checker.state.failure_message == rs_checker.state.failure_message
    assert rs_checker.state.failure_message == (
        "Routability regressed: 0.200 < 0.300 (threshold). "
    )

    # Scenario 3: convergence message (seed + two identical-iteration stalls
    # reaches stall_limit=2).
    py_checker, rs_checker = _new_checkers({})
    for checker in (py_checker, rs_checker):
        _routability_result(checker, {"N1", "N2"}, 10, {"N1", "N2"}, 0.95, 2)
        _routability_result(checker, {"N1", "N2"}, 10, {"N1", "N2"}, 0.95, 2)
        _routability_result(checker, {"N1", "N2"}, 10, {"N1", "N2"}, 0.95, 2)
    assert py_checker.state.failure_message == rs_checker.state.failure_message
    assert rs_checker.state.failure_message == (
        "Routability converged: 2/10 nets routed with identical net set for 2 iterations"
    )


def test_is_converged_module_level_with_result_objects() -> None:
    """The shim extracts (success, length) from the dict values in order."""
    def result(success, length):
        return SimpleNamespace(success=success, length=length)

    cases = [
        ({}, None),
        ({"n1": result(True, 100.0), "n2": result(True, 200.0)}, None),
        ({"n1": result(True, 100.0), "n2": result(False, 200.0)}, None),
        ({"n1": result(False, 100.0), "n2": result(False, 200.0)},
         {"n1": result(False, 100.0), "n2": result(False, 200.0)}),
        ({"n1": result(False, 100.0), "n2": result(False, 200.0)},
         {"n1": result(False, 150.0), "n2": result(False, 200.0)}),
        ({"n1": result(False, 1e16), "n2": result(False, 1.0)},
         {"n1": result(False, 1e16), "n2": result(False, 0.0)}),
        ({"n1": result(False, 100.0)}, {}),
    ]
    for current, previous in cases:
        assert _conv.is_converged(current, previous) == _oracle.is_converged(
            current, previous
        ), f"is_converged module-level diverged for current={current!r} previous={previous!r}"


# ---------------------------------------------------------------------------
# preflight kernels
# ---------------------------------------------------------------------------


def _assert_component_area_ratio(dims, bw, bh, keepout_dims):
    ref = canon(_ref_component_area_ratio(dims, bw, bh, keepout_dims))
    got = canon(RS_COMPONENT_AREA_RATIO(dims, bw, bh, keepout_dims))
    assert ref == got, (
        f"component_area_ratio mismatch: dims={dims!r} board=({bw!r},{bh!r}) "
        f"keepouts={keepout_dims!r}\n  ref={ref}\n  got={got}"
    )


def _random_dims(rng, n):
    return [(rng.uniform(0.1, 50.0), rng.uniform(0.1, 50.0)) for _ in range(n)]


def test_component_area_ratio_crafted() -> None:
    _assert_component_area_ratio([], 100.0, 80.0, [])
    _assert_component_area_ratio([(10.0, 5.0), (1.0, 1.0), (2.0, 2.0)], 100.0, 80.0, [])
    _assert_component_area_ratio([(10.0, 5.0)], 100.0, 80.0, [(3.0, 4.0)])
    # usable == 0 (board fully covered by keepouts) -> ratio 1.0 (WARN)
    _assert_component_area_ratio([(1.0, 1.0)], 10.0, 10.0, [(10.0, 10.0)])
    # usable < 0 -> ratio 1.0
    _assert_component_area_ratio([(1.0, 1.0)], 10.0, 10.0, [(20.0, 20.0)])
    # PASS / WARN / FAIL bands
    _assert_component_area_ratio([(1.0, 1.0)], 10.0, 10.0, [])          # 0.01 PASS
    _assert_component_area_ratio([(8.0, 8.0)], 10.0, 10.0, [])          # 0.64 PASS
    _assert_component_area_ratio([(8.5, 8.5)], 10.0, 10.0, [])          # 0.7225 WARN
    _assert_component_area_ratio([(10.0, 10.0)], 10.0, 10.0, [])        # 1.0 FAIL


def test_component_area_ratio_randomized() -> None:
    rng = random.Random(99)
    for _ in range(200):
        dims = _random_dims(rng, rng.randint(0, 8))
        keepouts = _random_dims(rng, rng.randint(0, 4))
        bw = rng.uniform(10.0, 200.0)
        bh = rng.uniform(10.0, 200.0)
        _assert_component_area_ratio(dims, bw, bh, keepouts)


def _assert_proximity_rule(wa, ha, wb, hb, max_d):
    ref = canon(_ref_proximity_rule(wa, ha, wb, hb, max_d))
    got = canon(RS_PROXIMITY_RULE(wa, ha, wb, hb, max_d))
    assert ref == got, (
        f"proximity_rule mismatch: ({wa!r},{ha!r}) vs ({wb!r},{hb!r}) max={max_d!r}\n"
        f"  ref={ref}\n  got={got}"
    )


def test_proximity_rule_crafted_and_randomized() -> None:
    cases = [
        (10.0, 5.0, 1.0, 1.0, 0.5),    # impossible
        (10.0, 5.0, 1.0, 1.0, 50.0),   # fine
        (10.0, 5.0, 1.0, 1.0, 3.0),    # boundary: 3.0 < 3.0 is False
        (1.0, 10.0, 1.0, 1.0, 5.0),    # min uses height arm
        (1.0, 1.0, 1.0, 1.0, 0.5),     # min((2)/2,(2)/2)=1.0
        (float("nan"), 1.0, 1.0, 1.0, 5.0),  # NaN first arm -> py_min keeps it
        (1.0, 1.0, float("nan"), 1.0, 5.0),
    ]
    for args in cases:
        _assert_proximity_rule(*args)
    rng = random.Random(7)
    for _ in range(200):
        args = tuple(rng.uniform(0.1, 100.0) for _ in range(5))
        _assert_proximity_rule(*args)


def test_zone_over_capacity_crafted_and_randomized() -> None:
    assert RS_ZONE_OVER_CAPACITY(20.0, 10.0, [(4.0, 4.0)]) == _ref_zone_over_capacity(
        20.0, 10.0, [(4.0, 4.0)]
    )
    # tiny zone: content 4.0 > 3.6 (90% of 4.0)
    assert RS_ZONE_OVER_CAPACITY(2.0, 2.0, [(4.0, 1.0)]) is True
    assert RS_ZONE_OVER_CAPACITY(2.0, 2.0, [(3.0, 1.0)]) is False  # 3.0 <= 3.6
    assert RS_ZONE_OVER_CAPACITY(2.0, 2.0, []) is False
    rng = random.Random(11)
    for _ in range(200):
        w, h = rng.uniform(0.1, 100.0), rng.uniform(0.1, 100.0)
        dims = _random_dims(rng, rng.randint(0, 6))
        ref = _ref_zone_over_capacity(w, h, dims)
        got = RS_ZONE_OVER_CAPACITY(w, h, dims)
        assert ref == got, f"zone_over_capacity mismatch: w={w!r} h={h!r} dims={dims!r}"


def test_loop_area_violation_crafted_and_randomized() -> None:
    assert RS_LOOP_AREA_VIOLATION(1.0, True, [(10.0, 5.0)]) == _ref_loop_area_violation(
        1.0, True, [(10.0, 5.0)]
    )
    assert RS_LOOP_AREA_VIOLATION(100.0, True, [(10.0, 5.0)]) is False
    assert RS_LOOP_AREA_VIOLATION(0.0, False, [(10.0, 5.0)]) is False  # falsy skip
    assert RS_LOOP_AREA_VIOLATION(1.0, False, [(10.0, 5.0)]) is False  # None -> falsy
    # NaN max_a is truthy but NaN < x is False
    assert RS_LOOP_AREA_VIOLATION(float("nan"), True, [(10.0, 5.0)]) is False
    rng = random.Random(13)
    for _ in range(200):
        max_a = rng.uniform(0.0, 100.0)
        dims = _random_dims(rng, rng.randint(0, 6))
        ref = _ref_loop_area_violation(max_a, True, dims)
        got = RS_LOOP_AREA_VIOLATION(max_a, True, dims)
        assert ref == got, f"loop_area_violation mismatch: max_a={max_a!r} dims={dims!r}"


def test_isolation_barrier_crafted_and_randomized() -> None:
    # hv board: barrier min(100,80)*6.5 = 520; 55 + 520 <= 7600 -> feasible
    assert RS_ISOLATION_BARRIER(
        [(10.0, 5.0), (1.0, 1.0), (2.0, 2.0)], 100.0, 80.0, 6.5
    ) == _ref_isolation_barrier([(10.0, 5.0), (1.0, 1.0), (2.0, 2.0)], 100.0, 80.0, 6.5)
    # small board: everything fills it -> barrier too large
    assert RS_ISOLATION_BARRIER([(10.0, 5.0)], 11.0, 11.0, 6.5) is True
    assert RS_ISOLATION_BARRIER([(1.0, 1.0)], 100.0, 80.0, 6.5) is False
    rng = random.Random(17)
    for _ in range(200):
        dims = _random_dims(rng, rng.randint(0, 6))
        bw, bh = rng.uniform(10.0, 200.0), rng.uniform(10.0, 200.0)
        ref = _ref_isolation_barrier(dims, bw, bh, 6.5)
        got = RS_ISOLATION_BARRIER(dims, bw, bh, 6.5)
        assert ref == got, f"isolation_barrier mismatch: dims={dims!r} board=({bw!r},{bh!r})"


# ---------------------------------------------------------------------------
# preflight module-level differentials (PreflightChecker.run)
# ---------------------------------------------------------------------------


def _make_component(ref, width, height, zone="", net_class=""):
    return SimpleNamespace(
        ref=ref, width=width, height=height, zone=zone, net_class=net_class
    )


def _check_signature(check) -> tuple:
    return (
        check.name,
        check.result.value if hasattr(check.result, "value") else check.result,
        check.message,
        canon(check.details),
    )


def _run_both(board, netlist, constraints):
    """Run both arms' PreflightChecker.run and compare every check field
    (time fields excluded — they are wall-clock)."""
    py_checker = _oracle.PreflightChecker()
    rs_checker = _pref.PreflightChecker()
    py_report = py_checker.run(board, netlist, constraints, None)
    rs_report = rs_checker.run(board, netlist, constraints, None)

    assert len(py_report.checks) == len(rs_report.checks) == 10
    for i, (py_c, rs_c) in enumerate(zip(py_report.checks, rs_report.checks)):
        assert _check_signature(py_c) == _check_signature(rs_c), (
            f"check #{i} diverged:\n  py={_check_signature(py_c)}\n  rs={_check_signature(rs_c)}"
        )
    assert py_report.overall.value == rs_report.overall.value
    assert py_report.passed == rs_report.passed
    assert rs_report.summary().startswith("Preflight Checks:")
    return rs_report


def test_preflight_run_full_report() -> None:
    """The full 10-check report, including the mixed-length keepout list that
    exercises the int-0 entries in the compensated keepout sum."""
    board = SimpleNamespace(
        width=100.0,
        height=80.0,
        keepouts=[[10, 10], [1, 2, 3, 4], [5, 6]],  # len-2 and len-3 -> 0; [1,2,3,4] -> 12
    )
    netlist = SimpleNamespace(
        components=[
            _make_component("U1", 10.0, 5.0, net_class="HighVoltage"),
            _make_component("R1", 1.0, 1.0),
            _make_component("C1", 2.0, 2.0, zone="Z1"),
        ],
        nets=[],
    )
    constraints = SimpleNamespace(
        component_groups=[
            SimpleNamespace(
                proximity_rules=[
                    SimpleNamespace(component_a="U1", component_b="R1", max_distance_mm=0.5),
                    SimpleNamespace(component_a="U1", component_b="C1", max_distance_mm=50.0),
                    SimpleNamespace(component_a="U1", component_b="MISSING", max_distance_mm=1.0),
                    SimpleNamespace(component_a="U1", component_b="C1", max_distance_mm=3.0),
                ]
            )
        ],
        critical_loops=[
            SimpleNamespace(max_area_mm2=1.0, pins=[("U1", "1")], name="L1"),
            SimpleNamespace(max_area_mm2=100.0, pins=[("U1", "1")], name="L2"),
            SimpleNamespace(max_area_mm2=1.0, pins=[("MISSING", "1")], name="L3"),
            SimpleNamespace(max_area_mm2=None, pins=[("U1", "1")], name="L4"),
            SimpleNamespace(max_area_mm2=0.0, pins=[("U1", "1")], name="L5"),
            SimpleNamespace(nets=["X"], max_area_mm2=1.0, name="L6"),
            SimpleNamespace(max_area_mm2=1.0, name="L7"),
        ],
    )
    report = _run_both(board, netlist, constraints)
    # layer count fails (no stackup), constraint satisfiability fails
    # (2 impossible rules), loop area warns (L1), so overall == FAIL.
    by_name = {c.name: c for c in report.checks}
    assert by_name["Layer Count"].result.value == "fail"
    assert by_name["Constraint Satisfiability"].result.value == "fail"
    assert by_name["Constraint Satisfiability"].details == {
        "impossible": [
            "U1-R1: max 0.5mm < min 3.0mm",
            "U1-C1: max 3.0mm < min 3.5mm",
        ]
    }
    assert by_name["Loop Area Feasibility"].result.value == "warn"
    assert by_name["Component Area"].message == "Fill ratio 0.7%"
    assert report.overall.value == "fail"
    assert report.passed is False


def test_preflight_run_zone_capacity_violation() -> None:
    board = SimpleNamespace(
        width=100.0,
        height=80.0,
        keepouts=[],
        zones=[SimpleNamespace(name="Z1", width=2.0, height=2.0)],
    )
    netlist = SimpleNamespace(
        components=[
            _make_component("C1", 2.0, 2.0, zone="Z1"),
            _make_component("R1", 1.0, 1.0),
        ],
        nets=[],
    )
    report = _run_both(board, netlist, SimpleNamespace())
    by_name = {c.name: c for c in report.checks}
    assert by_name["Zone Capacity"].result.value == "fail"
    assert by_name["Zone Capacity"].message == "Zone Z1 over cap"


def test_preflight_run_component_area_warn_and_pass() -> None:
    board = SimpleNamespace(width=10.0, height=10.0, keepouts=[])
    warn_netlist = SimpleNamespace(
        components=[_make_component("R1", 8.5, 8.5)], nets=[]
    )
    warn_report = _run_both(board, warn_netlist, SimpleNamespace())
    assert {c.name: c.result.value for c in warn_report.checks}["Component Area"] == "warn"
    assert [c for c in warn_report.checks if c.name == "Component Area"][0].message == (
        "Fill ratio 72.2%"
    )

    pass_netlist = SimpleNamespace(
        components=[_make_component("R1", 1.0, 1.0)], nets=[]
    )
    pass_report = _run_both(board, pass_netlist, SimpleNamespace())
    assert {c.name: c.result.value for c in pass_report.checks}["Component Area"] == "pass"
    assert [c for c in pass_report.checks if c.name == "Component Area"][0].message == (
        "Fill ratio 1.0%"
    )


# ---------------------------------------------------------------------------
# derivation kernels
# ---------------------------------------------------------------------------


def _assert_derive_kernel(rs_fn, ref_fn, cases):
    for x in cases:
        ref = canon(ref_fn(x))
        got = canon(rs_fn(x))
        assert ref == got, f"derive mismatch for {x!r}: ref={ref} got={got}"


def test_derive_emi_max_dist() -> None:
    _assert_derive_kernel(
        RS_DERIVE_EMI,
        _ref_derive_emi,
        [0.0, 1.0, 4.0, 100.0, 0.25, 2.0, 1e6, 1e-6, 999.999, 7.0, float("nan"), float("inf")],
    )


def test_derive_thermal_clearance() -> None:
    _assert_derive_kernel(
        RS_DERIVE_THERMAL, _ref_derive_thermal, [0.0, 0.5, 1.0, 5.0, 0.1, 123.45, -2.0, float("nan")]
    )


def test_derive_si_max_placement_dist() -> None:
    _assert_derive_kernel(
        RS_DERIVE_SI, _ref_derive_si, [0.0, 1.0, 50.0, 100.0, 0.3, 77.7, float("nan"), float("inf")]
    )


def test_mains_voltage_class_boundaries() -> None:
    cases = [
        0.0, 50.0, 50.0001, 51.0, 130.0, 130.0001, 240.0, 264.0, 264.0001,
        265.0, 1e6, float("nan"), float("inf"), float("-inf"), -5.0,
    ]
    for v in cases:
        assert RS_MAINS_CLASS(v) == _ref_mains_voltage_class(v), f"mains class mismatch for {v!r}"
    assert _oracle._mains_voltage_to_class(240.0).name == _der._mains_voltage_to_class(240.0).name
    assert _der._mains_voltage_to_class(240.0).value == 4  # MAINS_240V


def test_extract_min_clearance() -> None:
    cases = [
        ("U1_min_clearance", 5.0),
        ("R1_min_clearance", 3.0),
        ("a_min_clearance_min_clearance", 5.0),
        ("loop1_max_dist", 8.0),
        ("hv_lv_isolation_mm", 3.0),
        ("_min_clearance", 1.0),
        ("U1_min_clearanceX", 2.0),
        ("", 0.0),
    ]
    for key, value in cases:
        ref = canon(_ref_extract_min_clearance(key, value))
        got = canon(RS_EXTRACT_MIN_CLEARANCE(key, value))
        assert ref == got, f"extract_min_clearance mismatch for ({key!r}, {value!r})"


# ---------------------------------------------------------------------------
# derivation module-level differentials
# ---------------------------------------------------------------------------


def test_derive_constraints_from_spec_full() -> None:
    from temper_placer.core.specification import (
        EMISpec,
        PcbSpecification,
        SafetySpec,
        SignalIntegritySpec,
        ThermalSpec,
    )

    spec = PcbSpecification(
        name="test",
        thermal=ThermalSpec(power_dissipation={"U1": 5.0, "R1": 0.5}),
        emi=EMISpec(max_loop_area_mm2={"loop1": 100.0, "loop2": 4.0}),
        signal_integrity=SignalIntegritySpec(max_length_mm={"NET1": 50.0}),
        safety=SafetySpec(mains_voltage_v=240, pollution_degree=2),
    )
    ref = canon(_oracle.derive_constraints_from_spec(spec, None))
    got = canon(_der.derive_constraints_from_spec(spec, None))
    assert ref == got, f"derive_constraints_from_spec diverged:\n  ref={ref}\n  got={got}"
    # got = ("dict", ((key, value), ...)) in insertion order; the EMI block
    # runs first, so loop1_max_dist is the first pair.
    first_key, first_value = got[1][0]
    assert first_key == ("str", "loop1_max_dist")
    assert first_value == ("float", (8.0).hex())


def test_derive_constraints_from_spec_no_safety_warns() -> None:
    from temper_placer.core.specification import (
        EMISpec,
        PcbSpecification,
        SignalIntegritySpec,
        ThermalSpec,
    )

    spec = PcbSpecification(
        name="no-safety",
        thermal=ThermalSpec(power_dissipation={}),
        emi=EMISpec(max_loop_area_mm2={}),
        signal_integrity=SignalIntegritySpec(max_length_mm={}),
        safety=None,
    )
    with pytest.warns(UserWarning, match="No safety spec"):
        got = _der.derive_constraints_from_spec(spec, None)
    with pytest.warns(UserWarning, match="No safety spec"):
        ref = _oracle.derive_constraints_from_spec(spec, None)
    assert canon(got) == canon(ref)
    assert got["hv_lv_isolation_mm"] == 6.5


def test_derive_constraints_from_spec_voltage_classes() -> None:
    from temper_placer.core.specification import (
        EMISpec,
        PcbSpecification,
        SafetySpec,
        SignalIntegritySpec,
        ThermalSpec,
    )

    for voltage, expected_name in [(50, "LOW_VOLTAGE"), (120, "MAINS_120V"),
                                   (240, "MAINS_240V"), (340, "HIGH_VOLTAGE")]:
        # both arms map the voltage to the same VoltageClass pyclass member
        assert _der._mains_voltage_to_class(voltage).name == expected_name
        assert _oracle._mains_voltage_to_class(voltage).name == expected_name
        spec = PcbSpecification(
            name="v",
            thermal=ThermalSpec(power_dissipation={}),
            emi=EMISpec(max_loop_area_mm2={}),
            signal_integrity=SignalIntegritySpec(max_length_mm={}),
            safety=SafetySpec(mains_voltage_v=voltage, pollution_degree=2),
        )
        ref = canon(_oracle.derive_constraints_from_spec(spec, None))
        got = canon(_der.derive_constraints_from_spec(spec, None))
        assert ref == got, f"voltage-class divergence at {voltage}V"
        assert got[1][0][0] == ("str", "hv_lv_isolation_mm")


def test_apply_derived_constraints_pcl() -> None:
    from temper_placer.pcl.constraints import ConstraintTier
    from temper_placer.pcl.parser import ConstraintCollection

    derived = {
        "loop1_max_dist": 8.0,
        "loop1_max_area_mm2": 100.0,
        "U1_min_clearance": 10.0,
        "R1_min_clearance": 3.0,
        "a_min_clearance_min_clearance": 5.0,
        "NET1_max_placement_dist": 33.3,
        "hv_lv_isolation_mm": 3.0,
    }
    py_pcl = ConstraintCollection(constraints=[])
    rs_pcl = ConstraintCollection(constraints=[])
    py_res = _oracle.apply_derived_constraints(None, derived, py_pcl)
    rs_res = _der.apply_derived_constraints(None, derived, rs_pcl)
    assert rs_res is rs_pcl

    def signature(pcl):
        return [
            (
                c.a,
                c.b,
                canon(c.min_distance_mm),
                c.tier.value if hasattr(c.tier, "value") else c.tier,
                c.because,
            )
            for c in pcl.constraints
        ]

    assert signature(py_res) == signature(rs_res)
    assert signature(rs_res) == [
        ("U1", "*", canon(10.0), ConstraintTier.STRONG.value,
         "Derived from thermal spec: U1 min clearance 10.0mm"),
        ("R1", "*", canon(3.0), ConstraintTier.STRONG.value,
         "Derived from thermal spec: R1 min clearance 3.0mm"),
        ("a", "*", canon(5.0), ConstraintTier.STRONG.value,
         "Derived from thermal spec: a min clearance 5.0mm"),
    ]


def test_apply_derived_constraints_none_returns_netlist() -> None:
    sentinel = object()
    assert _der.apply_derived_constraints(sentinel, {}) is sentinel
    assert _oracle.apply_derived_constraints(sentinel, {}) is sentinel


# ---------------------------------------------------------------------------
# Witnessed divergence (R1d honesty clause)
# ---------------------------------------------------------------------------

def test_none_max_distance_boundary() -> None:
    """`max_distance_mm=None` raises TypeError in BOTH arms (the oracle's
    `max_d < min_d` and the shim's `float(max_d)` both reject None) — but the
    exception messages differ. Recorded as the honest boundary, not hidden."""
    from types import SimpleNamespace as _SN

    comps = [_SN(ref="U1", width=10.0, height=5.0)]
    constraints = _SN(
        component_groups=[
            _SN(proximity_rules=[_SN(component_a="U1", component_b="U1", max_distance_mm=None)])
        ]
    )

    def run(checker, netlist):
        return checker._check_constraint_satisfiability(netlist, constraints)

    py_outcome = canon_call(lambda: run(_oracle.PreflightChecker(), _SN(components=comps, nets=[])))
    rs_outcome = canon_call(lambda: run(_pref.PreflightChecker(), _SN(components=comps, nets=[])))
    assert py_outcome[0] == "raised" and py_outcome[1] == "TypeError"
    assert rs_outcome[0] == "raised" and rs_outcome[1] == "TypeError"
    assert py_outcome != rs_outcome  # both raise TypeError; the message text differs
    assert "float()" in rs_outcome[2]
