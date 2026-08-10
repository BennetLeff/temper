"""R1a: behavioural A/B of the Phase-1 convergence Stage-engine port against
the pinned oracle.

Rust Orchestration Engine plan 2026-08-09-001, U1 (convergence): the four
``temper_placer.pipeline.convergence`` classes migrate to the
``temper-orchestration`` crate as pyclasses (``TerminationReason``,
``ConvergenceCriteria``, ``ConvergenceState``, ``ConvergenceChecker``); the
Python module keeps its full public API (four classes + the module-level
``is_converged``) as a delegation shim.

The pre-migration module is pinned VERBATIM as the oracle
(``tests/pipeline/_convergence_py_oracle.py`` — byte-identical to the
convergence section of ``_pipeline_feasibility_py_oracle.py``, which is
itself content-hash-pinned). Both arms are driven with IDENTICAL inputs;
every assertion is bit-exact (floats via ``float.hex()`` via ``canon``,
error parity via ``canon_call``).

Anti-vacuity: ``test_oracle_and_port_are_different_implementations`` asserts
the port is genuinely the Rust pyclasses (``__module__``), not the shim
resolving back onto itself.

Time handling: ``check_timeout``/``get_elapsed_seconds`` are wall-clock.
The randomized sequences therefore pin ``timeout_seconds`` to ``{0.0}``
(always fires: elapsed >= 0) or ``>= 60`` (never fires: elapsed is
milliseconds), so both arms agree deterministically.

Message parity: the regression/convergence ``failure_message`` f-strings
render floats with Python's ``:.3f``; the Rust side renders them by calling
CPython's ``format()`` builtin, so parity is by identity, not by
coincidence of formatter implementations.
"""

from __future__ import annotations

import hashlib
import random
from pathlib import Path

import temper_orchestration as _to

from temper_placer.pipeline import convergence as _conv
from tests.core._contract_canon import canon, canon_call
from tests.pipeline import _convergence_py_oracle as _oracle


def _rs_cls(name: str):
    """Lazy access to a Rust class so the suite collects (and fails with a
    clear assertion) BEFORE the port exists — the G1 RED state."""
    cls = getattr(_to, name, None)
    assert cls is not None, (
        f"temper_orchestration.{name} is missing: the Rust port has not been "
        "built (G1 RED). Rebuild via maturin develop after convergence.rs lands."
    )
    return cls

# ---------------------------------------------------------------------------
# The oracle must stay verbatim
# ---------------------------------------------------------------------------

_ORACLE_PATH = Path(__file__).with_name("_convergence_py_oracle.py")
_PINNED_BODY_SHA256 = "cd950ad4e4a8907105373a17e008e02af833700182945655c8ea6c8c0de21956"
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
    """Anti-vacuity: the port must be the Rust pyclasses, not the shim."""
    assert _conv is not _oracle
    assert _conv.ConvergenceChecker is not _oracle.ConvergenceChecker
    assert _conv.ConvergenceCriteria is not _oracle.ConvergenceCriteria
    assert _conv.ConvergenceState is not _oracle.ConvergenceState
    assert _conv.TerminationReason is not _oracle.TerminationReason
    assert _conv.is_converged is not _oracle.is_converged
    # The port is genuinely Rust: the pyclasses live in the extension module.
    assert _conv.ConvergenceChecker.__module__ == "temper_orchestration"
    assert _conv.ConvergenceCriteria.__module__ == "temper_orchestration"
    assert _conv.ConvergenceState.__module__ == "temper_orchestration"
    assert _conv.TerminationReason.__module__ == "temper_orchestration"
    # The shim still carries the `_rs` delegation seam the feasibility
    # differential relies on.
    assert hasattr(_conv, "_rs")
    assert _conv._rs is _to


# ---------------------------------------------------------------------------
# Value / default matching
# ---------------------------------------------------------------------------

_TERMINATION_VALUES = {
    "SUCCESS": "success",
    "MAX_ITERATIONS": "max_iterations",
    "TIMEOUT": "timeout",
    "INFEASIBLE": "infeasible",
    "NO_PROGRESS": "no_progress",
    "USER_ABORT": "user_abort",
    "ROUTABILITY_REGRESSION": "routability_regression",
    "ROUTABILITY_CONVERGED": "routability_converged",
}


def test_termination_reason_members_and_values_match() -> None:
    rs_reason = _rs_cls("TerminationReason")
    for name, value in _TERMINATION_VALUES.items():
        assert getattr(rs_reason, name).value == value
        assert getattr(_oracle.TerminationReason, name).value == value
    # repr/str shapes match the Enum contract the differential relies on.
    assert "ROUTABILITY_CONVERGED" in repr(rs_reason.ROUTABILITY_CONVERGED)
    assert str(rs_reason.SUCCESS) == str(_oracle.TerminationReason.SUCCESS)
    # membership equality against a non-member is False on both sides
    assert (rs_reason.SUCCESS == "success") is False
    assert (_oracle.TerminationReason.SUCCESS == "success") is False


_CRITERIA_FIELDS = [
    "max_iterations",
    "max_refinement_iterations",
    "timeout_seconds",
    "phase_timeout_seconds",
    "max_overlap_mm2",
    "max_boundary_violation_mm",
    "min_routing_completion",
    "min_manufacturing_margin_mm",
    "min_loss_improvement",
    "stagnation_epochs",
]


def _criteria_signature(criteria) -> tuple:
    return tuple(canon(getattr(criteria, f)) for f in _CRITERIA_FIELDS)


def test_criteria_defaults_match() -> None:
    assert _criteria_signature(_conv.ConvergenceCriteria()) == _criteria_signature(
        _oracle.ConvergenceCriteria()
    )


def test_criteria_kwargs_match() -> None:
    rng = random.Random(20260809)
    for _ in range(40):
        kwargs = {
            "max_iterations": rng.randint(0, 200),
            "max_refinement_iterations": rng.randint(0, 200),
            "timeout_seconds": rng.choice([0.0, rng.uniform(60.0, 1e5)]),
            "phase_timeout_seconds": rng.uniform(0.0, 1e4),
            "max_overlap_mm2": rng.uniform(0.0, 1.0),
            "max_boundary_violation_mm": rng.uniform(0.0, 1.0),
            "min_routing_completion": rng.uniform(0.0, 1.0),
            "min_manufacturing_margin_mm": rng.uniform(0.0, 1.0),
            "min_loss_improvement": rng.uniform(0.0, 1.0),
            "stagnation_epochs": rng.randint(0, 2000),
        }
        rs = _conv.ConvergenceCriteria(**kwargs)
        py = _oracle.ConvergenceCriteria(**kwargs)
        assert _criteria_signature(rs) == _criteria_signature(py), f"kwargs={kwargs!r}"


# ---------------------------------------------------------------------------
# Shared driver helpers (mirror the feasibility differential's conventions)
# ---------------------------------------------------------------------------


def _preinit(checker) -> None:
    """Pre-initialize the routability-regression state exactly like the real
    callers do (both arms raise AttributeError on a truly fresh state)."""
    checker.state._best_routed_nets = None
    checker.state._best_routability = None
    checker.state._stall_count = 0


def _new_checker_pair(criteria_kwargs: dict) -> tuple:
    py_criteria = _oracle.ConvergenceCriteria(**criteria_kwargs)
    rs_criteria = _conv.ConvergenceCriteria(**criteria_kwargs)
    py_checker = _oracle.ConvergenceChecker(py_criteria)
    rs_checker = _conv.ConvergenceChecker(rs_criteria)
    _preinit(py_checker)
    _preinit(rs_checker)
    return py_checker, rs_checker


def _snapshot(checker) -> dict:
    s = checker.state
    return {
        "iteration": s.iteration,
        "loss_history": [canon(x) for x in s.loss_history],
        "best_loss": canon(s.best_loss),
        "epochs_since_improvement": s.epochs_since_improvement,
        "terminated": s.terminated,
        "reason": s.termination_reason.value if s.termination_reason is not None else None,
        "message": s.failure_message,
        "best_routed": (
            sorted(s._best_routed_nets)
            if getattr(s, "_best_routed_nets", None) is not None
            else None
        ),
        "best_ratio": canon(getattr(s, "_best_routability", None)),
        "stall": getattr(s, "_stall_count", 0),
    }


def _assert_snapshots_equal(py_checker, rs_checker, label: str) -> None:
    py_snap = _snapshot(py_checker)
    rs_snap = _snapshot(rs_checker)
    assert py_snap == rs_snap, f"state diverged after {label}\n  py={py_snap}\n  rs={rs_snap}"


def _random_metrics(rng) -> dict[str, float]:
    keys = ["overlap_mm2", "boundary_violation_mm", "routing_completion",
            "manufacturing_margin_mm"]
    chosen = [k for k in keys if rng.random() < 0.7]
    metrics = {}
    for k in chosen:
        if k == "routing_completion":
            metrics[k] = rng.choice([0.0, rng.uniform(0.0, 1.5)])
        elif k == "manufacturing_margin_mm":
            metrics[k] = rng.uniform(0.0, 0.2)
        else:
            metrics[k] = rng.choice([0.0, rng.uniform(0.0, 0.05), float("nan")])
    return metrics


def _random_routability_args(rng) -> dict:
    nets = ["N1", "N2", "N3", "N4", "N5", "N6"]
    routed = frozenset(n for n in nets if rng.random() < 0.5)
    prev = frozenset(n for n in nets if rng.random() < 0.5) if rng.random() < 0.7 else None
    return {
        "routed_nets": routed,
        "total_nets": rng.randint(0, 12),
        "previous_routed_nets": prev,
        "regression_threshold": rng.uniform(0.5, 1.5),
        "stall_limit": rng.randint(1, 3),
    }


def _apply_op(checker, op: str, args: dict) -> object:
    """Apply a single operation to ONE checker and return the outcome."""
    if op == "increment_iteration":
        return canon_call(checker.increment_iteration)
    if op == "record_loss":
        return canon_call(checker.record_loss, args["loss"])
    if op == "check_iteration_limit":
        return canon_call(checker.check_iteration_limit)
    if op == "check_timeout":
        return canon_call(checker.check_timeout)
    if op == "check_stagnation":
        return canon_call(checker.check_stagnation)
    if op == "check_all":
        return canon_call(checker.check_all)
    if op == "check_success":
        return canon_call(checker.check_success, args["metrics"])
    if op == "mark_infeasible":
        return canon_call(checker.mark_infeasible, args["message"])
    if op == "mark_user_abort":
        return canon_call(checker.mark_user_abort)
    if op == "check_routability_regression":
        return canon_call(
            checker.check_routability_regression,
            args["routed_nets"],
            args["total_nets"],
            args["previous_routed_nets"],
            args["regression_threshold"],
            args["stall_limit"],
        )
    if op == "reset":
        return canon_call(checker.reset)
    raise AssertionError(f"unknown op {op!r}")


# ---------------------------------------------------------------------------
# Explicit deterministic sequences (bit-exact, hand-picked)
# ---------------------------------------------------------------------------


def test_record_loss_sequence_bit_exact() -> None:
    py_checker, rs_checker = _new_checker_pair({"min_loss_improvement": 0.01})
    losses = [100.0, 90.0, 99.5, 89.0, 89.0, 88.0, 100.0, float("nan"),
              -5.0, float("-inf"), float("inf"), 1e300, 1e-300]
    for loss in losses:
        py_out = canon_call(py_checker.record_loss, loss)
        rs_out = canon_call(rs_checker.record_loss, loss)
        assert py_out == rs_out, f"record_loss outcome diverged for {loss!r}"
        _assert_snapshots_equal(py_checker, rs_checker, f"record_loss({loss!r})")


def test_record_loss_zero_best_error_parity() -> None:
    """best_loss == 0.0 raises ZeroDivisionError in BOTH arms (CPython's
    float division), with identical type and message, and the loss was
    appended BEFORE the raise on both sides."""
    py_checker, rs_checker = _new_checker_pair({})
    for checker in (py_checker, rs_checker):
        checker.state.best_loss = 0.0
        checker.state.epochs_since_improvement = 3
    py_out = canon_call(py_checker.record_loss, 10.0)
    rs_out = canon_call(rs_checker.record_loss, 10.0)
    assert py_out == rs_out
    assert py_out[0] == "raised" and py_out[1] == "ZeroDivisionError"
    _assert_snapshots_equal(py_checker, rs_checker, "record_loss(10.0) over best=0.0")


def test_check_success_metrics_sets_bit_exact() -> None:
    py_checker, rs_checker = _new_checker_pair({})
    metric_sets = [
        {"overlap_mm2": 0.0, "boundary_violation_mm": 0.0,
         "routing_completion": 1.0, "manufacturing_margin_mm": 0.1},
        {"overlap_mm2": 1.0},
        {"routing_completion": 0.5},
        {"overlap_mm2": 0.0, "boundary_violation_mm": 0.0,
         "routing_completion": 1.0, "manufacturing_margin_mm": 0.0},
        {},
        {"overlap_mm2": float("nan")},
        {"overlap_mm2": 0.01, "boundary_violation_mm": 0.01,
         "routing_completion": 1.0, "manufacturing_margin_mm": 0.05},
        {"overlap_mm2": 0.0, "boundary_violation_mm": 0.0,
         "routing_completion": 1.0, "manufacturing_margin_mm": float("nan")},
        {"overlap_mm2": 0, "boundary_violation_mm": 0,
         "routing_completion": 1, "manufacturing_margin_mm": 1},  # ints coerce
    ]
    for metrics in metric_sets:
        py_out = canon_call(py_checker.check_success, metrics)
        rs_out = canon_call(rs_checker.check_success, metrics)
        assert py_out == rs_out, f"check_success diverged for {metrics!r}"
        _assert_snapshots_equal(py_checker, rs_checker, f"check_success({metrics!r})")


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
    py_checker, rs_checker = _new_checker_pair({})
    for routed, total, prev, thr, stall in _ROUTABILITY_SEQUENCE:
        prev_arg = frozenset(prev) if prev is not None else None
        py_out = canon_call(
            py_checker.check_routability_regression,
            frozenset(routed), total, prev_arg, thr, stall,
        )
        rs_out = canon_call(
            rs_checker.check_routability_regression,
            frozenset(routed), total, prev_arg, thr, stall,
        )
        assert py_out == rs_out, (
            f"routability return diverged for routed={sorted(routed)} total={total} "
            f"prev={prev} thr={thr} stall={stall}\n  py={py_out}\n  rs={rs_out}"
        )
        _assert_snapshots_equal(
            py_checker, rs_checker,
            f"routability(routed={sorted(routed)} total={total} prev={prev} thr={thr} stall={stall})",
        )


def test_check_routability_regression_messages() -> None:
    """Pin the rendered failure messages on both arms (formatting parity)."""
    # Scenario 1: regression with lost nets.
    py_checker, rs_checker = _new_checker_pair({})
    for checker in (py_checker, rs_checker):
        _apply_op(checker, "check_routability_regression",
                  {"routed_nets": frozenset({"N1", "N2", "N3", "N4", "N5"}),
                   "total_nets": 10, "previous_routed_nets": None,
                   "regression_threshold": 0.95, "stall_limit": 2})
    for checker in (py_checker, rs_checker):
        _apply_op(checker, "check_routability_regression",
                  {"routed_nets": frozenset({"N1", "N2"}),
                   "total_nets": 10, "previous_routed_nets": None,
                   "regression_threshold": 0.5, "stall_limit": 2})
    assert py_checker.state.failure_message == rs_checker.state.failure_message
    assert "Routability regressed: 0.200 < 0.250 (threshold)." in (
        rs_checker.state.failure_message
    )
    assert "Lost nets: ['N3', 'N4', 'N5']" in rs_checker.state.failure_message

    # Scenario 2: regression with no lost nets.
    py_checker, rs_checker = _new_checker_pair({})
    for checker in (py_checker, rs_checker):
        _apply_op(checker, "check_routability_regression",
                  {"routed_nets": frozenset({"N1", "N2"}),
                   "total_nets": 10, "previous_routed_nets": None,
                   "regression_threshold": 0.95, "stall_limit": 2})
    for checker in (py_checker, rs_checker):
        _apply_op(checker, "check_routability_regression",
                  {"routed_nets": frozenset({"N1", "N2"}),
                   "total_nets": 10, "previous_routed_nets": None,
                   "regression_threshold": 1.5, "stall_limit": 2})
    assert py_checker.state.failure_message == rs_checker.state.failure_message
    assert rs_checker.state.failure_message == (
        "Routability regressed: 0.200 < 0.300 (threshold). "
    )

    # Scenario 3: convergence message.
    py_checker, rs_checker = _new_checker_pair({})
    for _ in range(3):
        for checker in (py_checker, rs_checker):
            _apply_op(checker, "check_routability_regression",
                      {"routed_nets": frozenset({"N1", "N2"}),
                       "total_nets": 10,
                       "previous_routed_nets": frozenset({"N1", "N2"}),
                       "regression_threshold": 0.95, "stall_limit": 2})
    assert py_checker.state.failure_message == rs_checker.state.failure_message
    assert rs_checker.state.failure_message == (
        "Routability converged: 2/10 nets routed with identical net set for 2 iterations"
    )


def test_termination_and_priority_flags_bit_exact() -> None:
    """mark_infeasible / mark_user_abort / already-terminated check_all."""
    for kwargs in ({}, {"timeout_seconds": 0.0}):
        py_checker, rs_checker = _new_checker_pair(kwargs)
        for checker in (py_checker, rs_checker):
            checker.mark_infeasible("Constraints impossible")
        _assert_snapshots_equal(py_checker, rs_checker, "mark_infeasible")
        assert rs_checker.state.termination_reason.value == "infeasible"
        # check_all on an already-terminated state stays True and keeps reason.
        py_out = canon_call(py_checker.check_all)
        rs_out = canon_call(rs_checker.check_all)
        assert py_out == rs_out
        assert rs_out == ("ok", ("bool", True))
        _assert_snapshots_equal(py_checker, rs_checker, "check_all after infeasible")

        py_checker, rs_checker = _new_checker_pair(kwargs)
        for checker in (py_checker, rs_checker):
            checker.mark_user_abort()
        _assert_snapshots_equal(py_checker, rs_checker, "mark_user_abort")
        assert rs_checker.state.failure_message == "User aborted pipeline"


# ---------------------------------------------------------------------------
# G2: randomized ConvergenceState inputs, bit-exact (reason, message) parity
# ---------------------------------------------------------------------------


_TERM_REASONS = [
    None,
    "SUCCESS", "MAX_ITERATIONS", "TIMEOUT", "INFEASIBLE",
    "NO_PROGRESS", "USER_ABORT", "ROUTABILITY_REGRESSION", "ROUTABILITY_CONVERGED",
]

_OPS = [
    "increment_iteration", "record_loss", "check_stagnation",
    "check_iteration_limit", "check_success", "check_all",
    "check_routability_regression", "mark_infeasible", "mark_user_abort", "reset",
]


def _random_state_spec(rng) -> dict:
    """Generate a random ConvergenceState field set (once per trial, applied
    identically to both arms)."""
    return {
        "iteration": rng.randint(0, 30),
        "loss_history": [
            rng.choice([0.0, rng.uniform(-100.0, 1e6), float("nan"), float("inf")])
            for _ in range(rng.randint(0, 6))
        ],
        "best_loss": rng.choice([float("inf"), rng.uniform(0.0, 1e6)]),
        "epochs_since_improvement": rng.randint(0, 12),
        "terminated": rng.random() < 0.3,
        "reason_name": rng.choice(_TERM_REASONS),
        "failure_message": None if rng.random() < 0.5 else f"msg-{rng.randint(0, 9)}",
    }


def _apply_state(checker, spec: dict, enum) -> None:
    """Set the same state fields on one checker arm (enum is the arm's
    TerminationReason class)."""
    s = checker.state
    s.iteration = spec["iteration"]
    s.loss_history = list(spec["loss_history"])
    s.best_loss = spec["best_loss"]
    s.epochs_since_improvement = spec["epochs_since_improvement"]
    s.terminated = spec["terminated"]
    s.termination_reason = (
        None
        if spec["reason_name"] is None
        else getattr(enum, spec["reason_name"])
    )
    s.failure_message = spec["failure_message"]
    _preinit(checker)


def test_randomized_checker_sequences_bit_exact() -> None:
    """120 trials: random criteria + random state + a random op sequence, both
    arms driven identically, every return value AND every post-op state
    snapshot compared bit-exact. This is the G2 100+ randomized-input arm."""
    rng = random.Random(20260809)
    for trial in range(120):
        timeout = rng.choice([0.0, rng.uniform(60.0, 1e5)])
        criteria_kwargs = {
            "max_iterations": rng.randint(0, 8),
            "max_refinement_iterations": rng.randint(0, 8),
            "timeout_seconds": timeout,
            "phase_timeout_seconds": rng.uniform(0.0, 1e4),
            "max_overlap_mm2": rng.uniform(0.0, 0.05),
            "max_boundary_violation_mm": rng.uniform(0.0, 0.05),
            "min_routing_completion": rng.uniform(0.0, 1.0),
            "min_manufacturing_margin_mm": rng.uniform(0.0, 0.2),
            "min_loss_improvement": rng.uniform(0.0, 1.0),
            "stagnation_epochs": rng.randint(0, 6),
        }
        py_checker, rs_checker = _new_checker_pair(criteria_kwargs)

        spec = _random_state_spec(rng)
        _apply_state(py_checker, spec, _oracle.TerminationReason)
        _apply_state(rs_checker, spec, _conv.TerminationReason)

        n_ops = rng.randint(3, 14)
        for _ in range(n_ops):
            op = rng.choice(_OPS)
            if op == "record_loss":
                args = {"loss": rng.choice([rng.uniform(-100.0, 1e6), float("nan"),
                                            float("inf")])}
            elif op == "check_success":
                args = {"metrics": _random_metrics(rng)}
            elif op == "check_routability_regression":
                args = _random_routability_args(rng)
            elif op == "mark_infeasible":
                args = {"message": f"infeasible-{rng.randint(0, 9)}"}
            else:
                args = {}

            py_out = _apply_op(py_checker, op, args)
            rs_out = _apply_op(rs_checker, op, args)
            assert py_out == rs_out, (
                f"[trial {trial}] op {op} outcome diverged (args={args!r})\n"
                f"  py={py_out}\n  rs={rs_out}"
            )
            if op == "reset":
                # reset() drops the oracle's lazily-created _best_* attrs;
                # re-initialize exactly like the callers do.
                _preinit(py_checker)
                _preinit(rs_checker)
            _assert_snapshots_equal(py_checker, rs_checker, f"trial {trial} op {op}")


def test_is_converged_shim_matches_oracle() -> None:
    """The shim keeps the module-level is_converged helper (delegating to the
    crate's is_converged kernel); the oracle's version is the inline Python.
    SimpleNamespace result objects exercise the (success, length) extraction
    in dict order (order is load-bearing for the compensated sum)."""
    from types import SimpleNamespace

    def result(success, length):
        return SimpleNamespace(success=success, length=length)

    cases = [
        ({}, None),
        ({"n1": result(True, 100.0), "n2": result(True, 200.0)}, None),
        ({"n1": result(True, 100.0), "n2": result(False, 200.0)}, None),
        ({"n1": result(False, 100.0), "n2": result(False, 200.0)},
         {"n1": result(False, 100.0), "n2": result(False, 200.0)}),
        ({"n1": result(False, 1e16), "n2": result(False, 1.0)},
         {"n1": result(False, 1e16), "n2": result(False, 0.0)}),
        ({"n1": result(False, 100.0)}, {}),
    ]
    for current, previous in cases:
        assert _conv.is_converged(current, previous) == _oracle.is_converged(
            current, previous
        ), f"is_converged diverged for current={current!r} previous={previous!r}"


def test_convergence_state_construct_and_fields() -> None:
    """ConvergenceState is directly constructible (start_time as float
    seconds per the plan's Rust API) and its fields round-trip through the
    pyclass getters/setters."""
    s = _conv.ConvergenceState(1234.5)
    assert s.start_time == 1234.5
    assert s.iteration == 0
    assert s.loss_history == []
    assert s.best_loss == float("inf")
    assert s.epochs_since_improvement == 0
    assert s.terminated is False
    assert s.termination_reason is None
    assert s.failure_message is None
    s.iteration = 3
    s.loss_history = [1.0, 2.0]
    s.termination_reason = _conv.TerminationReason.NO_PROGRESS
    assert s.iteration == 3
    assert s.loss_history == [1.0, 2.0]
    assert s.termination_reason == _conv.TerminationReason.NO_PROGRESS
    assert s.termination_reason.value == "no_progress"


def test_checker_state_reset_creates_fresh_state() -> None:
    py_checker, rs_checker = _new_checker_pair({})
    for checker in (py_checker, rs_checker):
        checker.increment_iteration()
        checker.record_loss(10.0)
        checker.reset()
    _assert_snapshots_equal(py_checker, rs_checker, "reset")
    assert rs_checker.state.iteration == 0
    assert rs_checker.state.loss_history == []
    assert not rs_checker.state.terminated
