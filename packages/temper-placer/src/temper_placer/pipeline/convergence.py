"""Convergence criteria and early termination for pipeline.

This module defines when the pipeline should stop iterating, including:
- Success conditions (all phases pass, routing verified, manufacturing OK)
- Failure conditions (max iterations, timeout, infeasibility, stagnation)

This module is a delegation shim. The four classes -- ``TerminationReason``,
``ConvergenceCriteria``, ``ConvergenceState``, ``ConvergenceChecker`` -- are
Rust pyclasses in the ``temper-orchestration`` crate (Phase-1 of the Rust
orchestration engine, plan 2026-08-09-001; bit-identical parity pinned by
``tests/pipeline/test_convergence_rust_differential.py`` against the verbatim
pre-migration oracle ``tests/pipeline/_convergence_py_oracle.py``). The
public API is unchanged: the four classes plus the module-level
``is_converged`` helper, whose (success, length) extraction and compensated
``sum`` compute still delegate to the crate's ``is_converged`` kernel
(``feasibility.rs``), keeping dict insertion order (order is load-bearing
for the compensated summation).
"""

import temper_orchestration as _rs

TerminationReason = _rs.TerminationReason
ConvergenceCriteria = _rs.ConvergenceCriteria
ConvergenceState = _rs.ConvergenceState
ConvergenceChecker = _rs.ConvergenceChecker


def is_converged(current_results: dict, previous_results: dict | None) -> bool:
    """Check if routing results have converged.

    Converged if:
    1. Perfect routing achieved.
    2. Results are identical to previous iteration (stagnation).
    """
    if not current_results:
        return False

    # 1. Look for perfect routing
    all_success = all(r.success for r in current_results.values())
    if all_success:
        return True

    if previous_results is None:
        return False

    # 2. Check for stagnation (identical success rate and total length).
    # Using length as proxy for path change. The decision kernel
    # `is_converged` replicates the oracle's compensated builtin `sum()`
    # bit-exactly, so the (success, length) pairs cross in dict order
    # (order is load-bearing for the compensated summation).
    current_pairs = [(bool(r.success), float(r.length)) for r in current_results.values()]
    previous_pairs = [(bool(r.success), float(r.length)) for r in previous_results.values()]
    return bool(_rs.is_converged(current_pairs, previous_pairs))


__all__ = [
    "TerminationReason",
    "ConvergenceCriteria",
    "ConvergenceState",
    "ConvergenceChecker",
    "is_converged",
]
