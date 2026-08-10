"""Property-based tests (G4) and metamorphic relations (G5) for the Phase-1
convergence Stage-engine port (Rust Orchestration Engine plan 2026-08-09-001,
U1) — the ``temper_placer.pipeline.convergence`` classes as Rust pyclasses in
``temper-orchestration``.

Module-to-property map (G4 — every reachable behavior pinned):
- convergence.py -> P1 (iteration limit), P2 (timeout), P3 (success
  thresholds), P4 (stagnation), P5 (record_loss epoch monotonicity),
  P6 (check_all priority on an already-terminated state).
Plus MR1..MR4 metamorphic relations.

The plan's example property table (P1..P7 in the plan) is expressed against
an invented ``check(state) -> (reason, message)`` method that the real
pre-migration module never had; the real API is the method surface below
(``check_iteration_limit`` / ``check_timeout`` / ``check_success`` /
``check_stagnation`` / ``check_all`` / ``record_loss`` /
``check_routability_regression``), so each property is re-expressed over
that API. The intent (monotonicity, priority order, no-stagnation-without-
history, NaN never panics) is preserved; P7 (never panics on NaN/odd inputs)
is covered by the randomized differential suite's NaN/±inf draws.

Non-vacuity: every property routes through the ``_IMPL`` indirection below
and has a ``test_pN_fails_for_<mutant>`` companion re-running it via
``hypothesis.inner_test`` against a degenerate Python stand-in and asserting
AssertionError.

Exactness claims (G5): MR1 and MR4 are claimed BIT-EXACT (integer
comparisons; the routability stall counter is exact int arithmetic); MR2 and
MR3 are boolean-parity claims over state that is itself bit-exact.
"""

from __future__ import annotations

import pytest
import temper_orchestration as _to
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.pipeline import convergence as _conv

# The checker methods under test, routed through an indirection so mutation
# guards can swap in degenerate Python stand-ins (hypothesis.inner_test) and
# restore.
_IMPL = {
    "iter_limit": lambda c: c.check_iteration_limit(),
    "timeout": lambda c: c.check_timeout(),
    "success": lambda c, m: c.check_success(m),
    "stagnation": lambda c: c.check_stagnation(),
    "all": lambda c: c.check_all(),
    "record_loss": lambda c, x: c.record_loss(x),
    "routability": lambda c, r, t, p, thr, s: c.check_routability_regression(r, t, p, thr, s),
}

_FINITE = {"allow_nan": False, "allow_infinity": False}


@pytest.fixture
def _restore_impl():
    saved = dict(_IMPL)
    yield
    _IMPL.clear()
    _IMPL.update(saved)


def _preinit(checker) -> None:
    """The routability-regression bookkeeping attributes callers pre-set."""
    checker.state._best_routed_nets = None
    checker.state._best_routability = None
    checker.state._stall_count = 0


def _checker(criteria_kwargs: dict) -> _conv.ConvergenceChecker:
    checker = _conv.ConvergenceChecker(_conv.ConvergenceCriteria(**criteria_kwargs))
    _preinit(checker)
    return checker


# ---------------------------------------------------------------------------
# G4 — P1: iteration limit fires iff iteration >= max_iterations
# ---------------------------------------------------------------------------


@given(
    iteration=st.integers(min_value=0, max_value=20),
    max_iterations=st.integers(min_value=0, max_value=10),
)
@settings(max_examples=200, deadline=30000)
def test_p1_iteration_limit_fires_at_threshold(iteration, max_iterations):
    """P1. check_iteration_limit returns True iff iteration >= max_iterations,
    and a fire sets terminated + MAX_ITERATIONS.

    A kernel that never fires (or fires early) violates the threshold.
    """
    c = _checker({"max_iterations": max_iterations})
    c.state.iteration = iteration
    fired = _IMPL["iter_limit"](c)
    assert fired == (iteration >= max_iterations)
    if fired:
        assert c.state.terminated is True
        assert c.state.termination_reason.value == "max_iterations"
    else:
        assert c.state.terminated is False


def test_p1_fails_for_never_fires_mutant(_restore_impl):
    _IMPL["iter_limit"] = lambda c: False  # noqa: ARG005
    with pytest.raises(AssertionError):
        test_p1_iteration_limit_fires_at_threshold.hypothesis.inner_test(5, 5)


def test_p1_fails_for_early_fire_mutant(_restore_impl):
    _IMPL["iter_limit"] = lambda c: c.state.iteration >= c.criteria.max_iterations - 1  # noqa: ARG005
    with pytest.raises(AssertionError):
        # iteration 4 < max 5: the real kernel must NOT fire.
        test_p1_iteration_limit_fires_at_threshold.hypothesis.inner_test(4, 5)


# ---------------------------------------------------------------------------
# G4 — P2: timeout fires on a zero budget and not on a large one
# ---------------------------------------------------------------------------


@given(timeout=st.sampled_from([0.0, 60.0, 1e5]))
@settings(max_examples=200, deadline=30000)
def test_p2_timeout_fires_on_zero_budget(timeout):
    """P2. check_timeout returns True iff timeout_seconds == 0.0 (the elapsed
    time since construction is always >= 0 but always well under 60s).

    A kernel that always reports a timeout (or never does) violates one half.
    """
    c = _checker({"timeout_seconds": timeout})
    fired = _IMPL["timeout"](c)
    assert fired == (timeout == 0.0)
    if fired:
        assert c.state.termination_reason.value == "timeout"


def test_p2_fails_for_always_timeout_mutant(_restore_impl):
    _IMPL["timeout"] = lambda c: True  # noqa: ARG005
    with pytest.raises(AssertionError):
        test_p2_timeout_fires_on_zero_budget.hypothesis.inner_test(60.0)


def test_p2_fails_for_never_timeout_mutant(_restore_impl):
    _IMPL["timeout"] = lambda c: False  # noqa: ARG005
    with pytest.raises(AssertionError):
        test_p2_timeout_fires_on_zero_budget.hypothesis.inner_test(0.0)


# ---------------------------------------------------------------------------
# G4 — P3: success thresholds (all must pass; one violation fails)
# ---------------------------------------------------------------------------


_METRIC_QUAD = st.tuples(
    st.floats(min_value=0.0, max_value=1.0, **_FINITE),   # overlap
    st.floats(min_value=0.0, max_value=1.0, **_FINITE),   # boundary
    st.floats(min_value=0.0, max_value=1.5, **_FINITE),   # routing
    st.floats(min_value=0.0, max_value=0.5, **_FINITE),   # margin
)


@given(_METRIC_QUAD)
@settings(max_examples=200, deadline=30000)
def test_p3_success_threshold_decision(quad):
    """P3. With default criteria (max_overlap 0.01, max_boundary 0.01,
    min_routing 1.0, min_margin 0.05), check_success is True iff no metric
    violates its threshold; a fire sets SUCCESS and a no-fire never touches
    the termination reason.

    A kernel that returns a constant (or flips a comparison) violates the
    decision on at least one generated quad.
    """
    overlap, boundary, routing, margin = quad
    c = _checker({})
    metrics = {
        "overlap_mm2": overlap,
        "boundary_violation_mm": boundary,
        "routing_completion": routing,
        "manufacturing_margin_mm": margin,
    }
    ok = _IMPL["success"](c, metrics)
    expected = not (overlap > 0.01 or boundary > 0.01 or routing < 1.0 or margin < 0.05)
    assert ok == expected
    if ok:
        assert c.state.termination_reason.value == "success"
    else:
        assert c.state.termination_reason is None


def test_p3_fails_for_always_success_mutant(_restore_impl):
    _IMPL["success"] = lambda c, m: True  # noqa: ARG005
    with pytest.raises(AssertionError):
        # overlap 1.0 > 0.01 must fail.
        test_p3_success_threshold_decision.hypothesis.inner_test((1.0, 0.0, 1.0, 0.1))


def test_p3_fails_for_never_success_mutant(_restore_impl):
    _IMPL["success"] = lambda c, m: False  # noqa: ARG005
    with pytest.raises(AssertionError):
        # all metrics pass -> must succeed.
        test_p3_success_threshold_decision.hypothesis.inner_test((0.0, 0.0, 1.0, 0.1))


# ---------------------------------------------------------------------------
# G4 — P4: stagnation needs BOTH a history and enough epochs
# ---------------------------------------------------------------------------


@given(
    epochs=st.integers(min_value=0, max_value=12),
    stagnation=st.integers(min_value=0, max_value=8),
    history=st.booleans(),
)
@settings(max_examples=200, deadline=30000)
def test_p4_stagnation_needs_history_and_epochs(epochs, stagnation, history):
    """P4. check_stagnation fires iff the loss history is non-empty AND
    epochs_since_improvement >= stagnation_epochs; a fire sets NO_PROGRESS.

    A kernel that detects stagnation without history (or fires below the
    threshold) violates the property.
    """
    c = _checker({"stagnation_epochs": stagnation})
    if history:
        c.state.loss_history = [1.0]
    c.state.epochs_since_improvement = epochs
    fired = _IMPL["stagnation"](c)
    assert fired == (history and epochs >= stagnation)
    if fired:
        assert c.state.termination_reason.value == "no_progress"


def test_p4_fails_for_always_stagnation_mutant(_restore_impl):
    _IMPL["stagnation"] = lambda c: True  # noqa: ARG005
    with pytest.raises(AssertionError):
        # empty history -> never fires.
        test_p4_stagnation_needs_history_and_epochs.hypothesis.inner_test(0, 8, False)


def test_p4_fails_for_off_by_one_mutant(_restore_impl):
    _IMPL["stagnation"] = lambda c: bool(c.state.loss_history) and c.state.epochs_since_improvement > c.criteria.stagnation_epochs  # noqa: ARG005
    with pytest.raises(AssertionError):
        # epochs == stagnation (not >) must fire.
        test_p4_stagnation_needs_history_and_epochs.hypothesis.inner_test(3, 3, True)


# ---------------------------------------------------------------------------
# G4 — P5: record_loss epoch monotonicity (improvement resets, else +1)
# ---------------------------------------------------------------------------


@given(loss=st.floats(min_value=0.0, max_value=1e6, **_FINITE))
@settings(max_examples=200, deadline=30000)
def test_p5_record_loss_epoch_monotonicity(loss):
    """P5. From best_loss=100.0 and min_loss_improvement=0.01, record_loss
    appends to the history, resets epochs_since_improvement to 0 on a
    >= 1% improvement, and otherwise increments it by exactly one.

    A kernel that forgets to append (or increments on improvement) violates
    the monotonic bookkeeping.
    """
    c = _checker({"min_loss_improvement": 0.01})
    c.state.best_loss = 100.0
    c.state.epochs_since_improvement = 7
    _IMPL["record_loss"](c, loss)
    assert len(c.state.loss_history) == 1
    improved = (100.0 - loss) / 100.0 >= 0.01
    if improved:
        assert c.state.best_loss == loss
        assert c.state.epochs_since_improvement == 0
    else:
        assert c.state.best_loss == 100.0
        assert c.state.epochs_since_improvement == 8


def test_p5_fails_for_noop_mutant(_restore_impl):
    _IMPL["record_loss"] = lambda c, x: None  # noqa: ARG005
    with pytest.raises(AssertionError):
        test_p5_record_loss_epoch_monotonicity.hypothesis.inner_test(50.0)


def test_p5_fails_for_always_increment_mutant(_restore_impl):
    def always_increment(c, loss):
        c.state.loss_history.append(loss)
        c.state.epochs_since_improvement += 1
        return None

    _IMPL["record_loss"] = always_increment
    with pytest.raises(AssertionError):
        # loss 50.0 is a 50% improvement -> must reset, not increment.
        test_p5_record_loss_epoch_monotonicity.hypothesis.inner_test(50.0)


# ---------------------------------------------------------------------------
# G4 — P6: check_all on an already-terminated state preserves its reason
# ---------------------------------------------------------------------------


@given(reason_value=st.sampled_from(["success", "max_iterations", "timeout",
                                     "infeasible", "no_progress", "user_abort",
                                     "routability_regression", "routability_converged"]))
@settings(max_examples=200, deadline=30000)
def test_p6_check_all_preserves_existing_reason(reason_value):
    """P6. check_all on an already-terminated state returns True immediately
    and does NOT overwrite the existing termination reason (the priority
    order short-circuits at the "already terminated" gate).

    A kernel that clobbers the reason (or returns False on a terminated
    state) violates the priority contract.
    """
    c = _checker({})
    c.state.terminated = True
    c.state.termination_reason = _reason_for_value(reason_value)
    assert _IMPL["all"](c) is True
    assert c.state.termination_reason.value == reason_value


def _reason_for_value(value: str) -> _to.TerminationReason:
    for member in (
        "SUCCESS", "MAX_ITERATIONS", "TIMEOUT", "INFEASIBLE", "NO_PROGRESS",
        "USER_ABORT", "ROUTABILITY_REGRESSION", "ROUTABILITY_CONVERGED",
    ):
        candidate = getattr(_to.TerminationReason, member)
        if candidate.value == value:
            return candidate
    raise AssertionError(f"unknown reason value {value!r}")


def test_p6_fails_for_returns_false_mutant(_restore_impl):
    _IMPL["all"] = lambda c: False  # noqa: ARG005
    with pytest.raises(AssertionError):
        test_p6_check_all_preserves_existing_reason.hypothesis.inner_test("user_abort")


def test_p6_fails_for_reason_clobber_mutant(_restore_impl):
    def clobber(c):
        result = c.check_all()
        c.state.termination_reason = _to.TerminationReason.MAX_ITERATIONS
        return result

    _IMPL["all"] = clobber
    with pytest.raises(AssertionError):
        test_p6_check_all_preserves_existing_reason.hypothesis.inner_test("user_abort")


# ---------------------------------------------------------------------------
# Reachability (G4): each property's input class genuinely reaches the branch
# it names. A property that cannot fail is worse than an absent one.
# ---------------------------------------------------------------------------


def test_property_input_classes_are_discriminating() -> None:
    # P1 both halves reachable (threshold and below).
    c = _checker({"max_iterations": 5})
    c.state.iteration = 4
    assert c.check_iteration_limit() is False
    c.state.iteration = 5
    assert c.check_iteration_limit() is True

    # P2 zero vs large budget reachable.
    assert _checker({"timeout_seconds": 0.0}).check_timeout() is True
    assert _checker({"timeout_seconds": 1e5}).check_timeout() is False

    # P3 pass and fail halves reachable.
    c = _checker({})
    assert c.check_success(
        {"overlap_mm2": 0.0, "boundary_violation_mm": 0.0,
         "routing_completion": 1.0, "manufacturing_margin_mm": 0.1}
    ) is True
    c = _checker({})
    assert c.check_success({"overlap_mm2": 1.0}) is False

    # P4 empty-history and threshold halves reachable.
    c = _checker({"stagnation_epochs": 2})
    c.state.epochs_since_improvement = 2
    assert c.check_stagnation() is False  # no history
    c.state.loss_history = [1.0]
    assert c.check_stagnation() is True

    # P5 improvement-reset and increment halves reachable.
    c = _checker({"min_loss_improvement": 0.01})
    c.state.best_loss = 100.0
    c.state.epochs_since_improvement = 7
    c.record_loss(50.0)
    assert c.state.epochs_since_improvement == 0
    c.record_loss(99.5)
    assert c.state.epochs_since_improvement == 1

    # P6 terminated-state short-circuit reachable with reason preserved.
    c = _checker({})
    c.state.terminated = True
    c.state.termination_reason = _to.TerminationReason.USER_ABORT
    assert c.check_all() is True
    assert c.state.termination_reason.value == "user_abort"


# ---------------------------------------------------------------------------
# G5 — metamorphic relations
# ---------------------------------------------------------------------------


@given(max_iterations=st.integers(min_value=1, max_value=10))
@settings(max_examples=200, deadline=30000)
def test_mr1_iteration_firing_is_monotonic(max_iterations):
    """MR1 — monotonic iteration (plan MR1). Increasing iteration while
    holding everything else constant never flips a termination verdict from
    true to false: at iteration == max_iterations - 1 the limit has NOT
    fired, at max_iterations it HAS, and at max_iterations + 1 it still has.
    BIT-EXACT (integer comparisons)."""
    c = _checker({"max_iterations": max_iterations})
    c.state.iteration = max_iterations - 1
    assert _IMPL["iter_limit"](c) is False
    c.state.iteration = max_iterations
    assert _IMPL["iter_limit"](c) is True
    assert c.state.termination_reason.value == "max_iterations"
    c.state.terminated = False  # reset the side effect; re-check the boundary
    c.state.iteration = max_iterations + 1
    assert _IMPL["iter_limit"](c) is True


def test_mr1_fails_for_strict_greater_mutant(_restore_impl):
    def strict_greater(c):
        return c.state.iteration > c.criteria.max_iterations

    _IMPL["iter_limit"] = strict_greater
    with pytest.raises(AssertionError):
        # at iteration == max_iterations the real kernel fires, the mutant
        # does not — breaking monotonicity at the boundary.
        test_mr1_iteration_firing_is_monotonic.hypothesis.inner_test(3)


@given(stagnation=st.integers(min_value=1, max_value=5))
@settings(max_examples=200, deadline=30000)
def test_mr2_loss_improvement_resets_stall(stagnation):
    """MR2 — loss improvement resets stall (plan MR2). A state driven to the
    NoProgress threshold fires; recording a NEW loss that is a full
    improvement over best (min_loss_improvement = 1.0, loss 0.0) resets
    epochs_since_improvement to 0, so the same state no longer fires."""
    c = _checker({"stagnation_epochs": stagnation, "min_loss_improvement": 1.0})
    c.state.loss_history = [100.0]
    c.state.best_loss = 100.0
    c.state.epochs_since_improvement = stagnation - 1
    # one more non-improvement loss lands exactly AT the threshold.
    _IMPL["record_loss"](c, 100.0)
    assert _IMPL["stagnation"](c) is True
    # a 100% improvement resets the stall counter.
    _IMPL["record_loss"](c, 0.0)
    assert c.state.epochs_since_improvement == 0
    assert _IMPL["stagnation"](c) is False


def test_mr2_fails_for_no_reset_mutant(_restore_impl):
    def no_reset(c, loss):
        c.state.loss_history.append(loss)
        if c.state.best_loss == float("inf"):
            c.state.best_loss = loss
            c.state.epochs_since_improvement = 0
            return None
        improvement = (c.state.best_loss - loss) / c.state.best_loss
        if improvement < c.criteria.min_loss_improvement:
            c.state.epochs_since_improvement += 1
        return None

    _IMPL["record_loss"] = no_reset
    with pytest.raises(AssertionError):
        # stagnation=2: the improvement path leaves epochs at 2, so the
        # state still fires — violating MR2's reset claim.
        test_mr2_loss_improvement_resets_stall.hypothesis.inner_test(2)


@given(
    max_iterations=st.integers(min_value=1, max_value=8),
    refinement=st.integers(min_value=1, max_value=8),
    epochs=st.integers(min_value=0, max_value=10),
)
@settings(max_examples=200, deadline=30000)
def test_mr3_criteria_permutation_invariance(max_iterations, refinement, epochs):
    """MR3 — criteria permutation invariance (plan MR3). Swapping the
    max_iterations and max_refinement_iterations values leaves the checks
    that neither field governs — check_stagnation here — bit-identical
    (the two iteration-limit fields govern different checks; the epoch
    decision reads only stagnation_epochs)."""
    a = _checker({
        "max_iterations": max_iterations,
        "max_refinement_iterations": refinement,
        "stagnation_epochs": 2,
    })
    b = _checker({
        "max_iterations": refinement,
        "max_refinement_iterations": max_iterations,
        "stagnation_epochs": 2,
    })
    for c in (a, b):
        c.state.epochs_since_improvement = epochs
        c.state.loss_history = [1.0]
    assert _IMPL["stagnation"](a) == _IMPL["stagnation"](b)


def test_mr3_fails_for_wrong_field_mutant(_restore_impl):
    def reads_wrong_field(c):
        return c.state.epochs_since_improvement >= c.criteria.max_iterations

    _IMPL["stagnation"] = reads_wrong_field
    with pytest.raises(AssertionError):
        # max_iterations=3 vs refinement=1, epochs=2: the real kernel (2 >=
        # stagnation_epochs 2) fires on both arms; the wrong-field mutant
        # fires on one (2 >= 1) and not the other (2 >= 3).
        test_mr3_criteria_permutation_invariance.hypothesis.inner_test(3, 1, 2)


@given(
    net_count=st.integers(min_value=0, max_value=6),
    stall_limit=st.integers(min_value=1, max_value=3),
)
@settings(max_examples=200, deadline=30000)
def test_mr4_routability_stall_increment_and_reset(net_count, stall_limit):
    """MR4 — routability stall bookkeeping. After a first (seeding) call, an
    identical net set on the next call increments the stall counter (1, below
    any stall_limit the strategy draws), and a DIFFERENT net set resets it to
    0. BIT-EXACT (the counter is exact integer arithmetic)."""
    routed = frozenset(f"N{i}" for i in range(net_count))
    c = _checker({})
    assert _IMPL["routability"](c, routed, 10, None, 0.95, stall_limit) is False
    first_stall = _IMPL["routability"](c, routed, 10, routed, 0.95, stall_limit)
    assert c.state._stall_count == 1
    assert first_stall == (stall_limit == 1)
    # a different net set resets the stall counter.
    other = frozenset(f"X{i}" for i in range(net_count + 1))
    _IMPL["routability"](c, other, 10, routed, 0.95, stall_limit)
    assert c.state._stall_count == 0


def test_mr4_fails_for_no_increment_mutant(_restore_impl):
    def no_increment(c, routed, total, prev, thr, stall):
        result = c.check_routability_regression(routed, total, prev, thr, stall)
        c.state._stall_count = 0  # degenerate: never lets the stall accumulate
        return result

    _IMPL["routability"] = no_increment
    with pytest.raises(AssertionError):
        # net_count=2, stall_limit=2: the identical-set call must leave the
        # stall counter at 1.
        test_mr4_routability_stall_increment_and_reset.hypothesis.inner_test(2, 2)
