"""Differential test: explainability/logger.py compute (temper-io-types)
vs the pinned Python oracle.

Wave 4, Phase 5 — the explainability surface migration. The Rust migration
(reproducing ``temper_placer/explainability/logger.py``'s compute
bit-identically in the ``temper-io-types`` crate) is driven through the
delegation shim ``temper_placer.explainability.logger``; the
pre-migration implementation is pinned verbatim as the oracle
(``explain_oracle/logger_oracle.py``).

Migrated: ``should_log`` (interval gating with Python modulo semantics),
``significant_change`` (Euclidean distance via IEEE sqrt), and the
decision-construction logic of the four ``log_*`` methods (decision-type
selection, effective-reason generation, confidence-as-loss, default
phase/epoch/iteration). Enable/disable state, the context managers and
``trace.add`` remain Python runtime semantics.
"""

from __future__ import annotations

import math
import random

import temper_io_types as _rust

from tests.explainability.explain_oracle import logger_oracle as _oracle
from temper_placer.explainability.logger import DecisionLogger

# Module-scope RED arm.
assert hasattr(_rust, "explain_should_log")
assert hasattr(_rust, "explain_significant_change")
assert hasattr(_rust, "explain_log_position")
assert hasattr(_rust, "explain_log_rotation")
assert hasattr(_rust, "explain_log_heuristic")
assert hasattr(_rust, "explain_log_constraint")


def test_should_log_identical():
    oracle = _oracle.DecisionLogger()
    shim = DecisionLogger()
    for epoch in range(-20, 101):
        for interval in [1, 2, 3, 10, 100, 1000]:
            for is_final in [False, True]:
                assert shim.should_log(epoch, interval, is_final) == oracle.should_log(
                    epoch, interval, is_final
                )


def test_should_log_boundaries():
    logger = DecisionLogger()
    assert logger.should_log(0, 100) is True
    assert logger.should_log(50, 100) is False
    assert logger.should_log(100, 100) is True
    assert logger.should_log(999, 100) is False
    assert logger.should_log(123, 100, is_final=True) is True


def test_should_log_negative_epoch_modulo():
    """Python modulo: -5 % 100 == 95, so -5 with interval 100 is NOT a
    boundary (Rust '%' is remainder and would say -5 == 0)."""
    logger = DecisionLogger()
    assert logger.should_log(-5, 100) is False
    assert logger.should_log(-100, 100) is True  # -100 % 100 == 0
    assert logger.should_log(-5, 100) == _oracle.DecisionLogger().should_log(-5, 100)


def test_should_log_zero_interval_raises():
    import pytest

    logger = DecisionLogger()
    with pytest.raises(ZeroDivisionError):
        logger.should_log(10, 0, False)
    with pytest.raises(ZeroDivisionError):
        _oracle.DecisionLogger().should_log(10, 0, False)


def test_significant_change_identical():
    rng = random.Random(0x510)
    oracle = _oracle.DecisionLogger()
    shim = DecisionLogger()
    for _ in range(500):
        old = (rng.uniform(-100, 100), rng.uniform(-100, 100))
        new = (rng.uniform(-100, 100), rng.uniform(-100, 100))
        threshold = rng.uniform(0.0, 50.0)
        assert shim.significant_change(old, new, threshold) == oracle.significant_change(
            old, new, threshold
        )


def test_significant_change_boundary():
    logger = DecisionLogger()
    # sqrt(3^2 + 4^2) = 5.0 exactly.
    assert logger.significant_change((0, 0), (3, 4), 5.0) is True
    assert logger.significant_change((0, 0), (3, 4), 5.001) is False
    assert logger.significant_change((0, 0), (0, 0), 0.0) is True


def test_significant_change_nan():
    logger = DecisionLogger()
    assert logger.significant_change((float("nan"), 0), (1, 0), 0.5) is False


def test_log_position_constructs_update_vs_initial():
    oracle = _oracle.DecisionLogger()
    shim = DecisionLogger()
    shim.log_position("C1", (10.0, 20.0), reason="first")
    oracle.log_position("C1", (10.0, 20.0), reason="first")
    shim.log_position("C1", (12.0, 21.0), previous=(10.0, 20.0), reason="moved")
    oracle.log_position("C1", (12.0, 21.0), previous=(10.0, 20.0), reason="moved")
    _assert_traces_equal(shim.trace, oracle.trace)


def test_log_position_full_context():
    from temper_placer.explainability.decision import Alternative, DecisionPhase

    oracle = _oracle.DecisionLogger()
    shim = DecisionLogger()
    oracle.set_phase(DecisionPhase.ROUTING)
    shim.set_phase(DecisionPhase.ROUTING)
    oracle.set_epoch(42)
    shim.set_epoch(42)
    oracle.set_iteration(3)
    shim.set_iteration(3)
    alt = Alternative(value=(1, 1), rejection_reason="r", loss_if_chosen=0.5)
    shim.log_position("C1", (1, 2), previous=(0, 0), reason="why", constraint_refs=["c1"],
                      alternatives=[alt], loss_delta=1.75)
    oracle.log_position("C1", (1, 2), previous=(0, 0), reason="why", constraint_refs=["c1"],
                        alternatives=[alt], loss_delta=1.75)
    _assert_traces_equal(shim.trace, oracle.trace)


def test_log_rotation_identical():
    oracle = _oracle.DecisionLogger()
    shim = DecisionLogger()
    shim.log_rotation("Q1", 1, previous=0, reason="rot")
    oracle.log_rotation("Q1", 1, previous=0, reason="rot")
    shim.log_rotation("Q1", 2, reason="no prev")
    oracle.log_rotation("Q1", 2, reason="no prev")
    _assert_traces_equal(shim.trace, oracle.trace)


def test_log_heuristic_reason_generation():
    oracle = _oracle.DecisionLogger()
    shim = DecisionLogger()
    shim.log_heuristic("thermal_edge", "Q1", (5, 5), confidence=0.8)
    oracle.log_heuristic("thermal_edge", "Q1", (5, 5), confidence=0.8)
    shim.log_heuristic("thermal_edge", "Q2", (6, 6), reason="custom", confidence=0.2)
    oracle.log_heuristic("thermal_edge", "Q2", (6, 6), reason="custom", confidence=0.2)
    _assert_traces_equal(shim.trace, oracle.trace)
    d0 = shim.trace.decisions[0]
    assert d0.reason == "Placed by thermal_edge heuristic"
    assert d0.loss_contribution == 0.8
    assert d0.phase == shim.trace.decisions[0].phase
    assert d0.decision_type.value == "initial_position"


def test_log_constraint_reason_generation():
    oracle = _oracle.DecisionLogger()
    shim = DecisionLogger()
    shim.log_constraint_application("thermal.edge", ["Q1", "Q2"], "moved_to_edge")
    oracle.log_constraint_application("thermal.edge", ["Q1", "Q2"], "moved_to_edge")
    shim.log_constraint_application("spacing", ["R1"], "enforced", reason="explicit")
    oracle.log_constraint_application("spacing", ["R1"], "enforced", reason="explicit")
    _assert_traces_equal(shim.trace, oracle.trace)
    d0 = shim.trace.decisions[0]
    assert d0.reason == "Constraint thermal.edge moved_to_edge: affected Q1, Q2"
    assert d0.constraint_refs == ["thermal.edge"]


def test_disabled_logger_is_noop():
    shim = DecisionLogger()
    oracle = _oracle.DecisionLogger()
    shim.disable()
    oracle.disable()
    shim.log_position("C1", (1, 1))
    oracle.log_position("C1", (1, 1))
    assert len(shim.trace.decisions) == 0
    assert len(oracle.trace.decisions) == 0
    shim.enable()
    oracle.enable()
    shim.log_position("C1", (1, 1))
    oracle.log_position("C1", (1, 1))
    assert len(shim.trace.decisions) == 1


def test_phase_epoch_context_managers_restore():
    from temper_placer.explainability.decision import DecisionPhase

    shim = DecisionLogger()
    with shim.phase(DecisionPhase.ROUTING):
        assert shim.current_phase == DecisionPhase.ROUTING
    assert shim.current_phase == DecisionPhase.GEOMETRIC
    with shim.epoch(5):
        assert shim.current_epoch == 5
    assert shim.current_epoch is None


def _assert_traces_equal(a, b):
    assert len(a.decisions) == len(b.decisions)
    for da, db in zip(a.decisions, b.decisions):
        # NOTE: `id` and `timestamp` are deliberately NOT compared. They are
        # generated by Decision's own default_factory (uuid4 / datetime.now)
        # at construction time on each side, so even two identical pure-Python
        # loggers produce different ids — the differential pins the migrated
        # decision-construction fields (type selection, reason generation,
        # phase/epoch defaults), not the runtime-generated identity defaults.
        assert da.phase == db.phase
        assert da.decision_type == db.decision_type
        assert da.subject == db.subject
        assert _values_equal(da.value, db.value)
        assert _values_equal(da.previous_value, db.previous_value)
        assert da.reason == db.reason
        assert da.constraint_refs == db.constraint_refs
        assert da.loss_contribution == db.loss_contribution
        assert da.epoch == db.epoch
        assert da.iteration == db.iteration
        assert len(da.alternatives) == len(db.alternatives)
        for aa, ab in zip(da.alternatives, db.alternatives):
            assert _values_equal(aa.value, ab.value)
            assert aa.rejection_reason == ab.rejection_reason
            assert aa.constraint_violated == ab.constraint_violated
            assert aa.loss_if_chosen == ab.loss_if_chosen


def _values_equal(a, b):
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return list(a) == list(b)
    return a == b
