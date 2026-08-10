"""Convergence criteria and early termination for pipeline.

This module defines when the pipeline should stop iterating, including:
- Success conditions (all phases pass, routing verified, manufacturing OK)
- Failure conditions (max iterations, timeout, infeasibility, stagnation)

The feasibility/check compute (``record_loss`` improvement arithmetic,
``check_success`` thresholds, ``is_converged`` stagnation and
``check_routability_regression`` net-set decision + state) delegates to the
``temper-orchestration`` crate (``temper_orchestration.record_loss`` / ...
``check_routability_regression``), pinned bit-identically by
``tests/pipeline/test_pipeline_feasibility_rust_differential.py`` (oracle:
``tests/pipeline/_pipeline_feasibility_py_oracle.py``).
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

import temper_orchestration as _rs


class TerminationReason(Enum):
    """Enumeration of reasons why the pipeline terminated.

    Attributes:
        SUCCESS: All phases completed successfully
        MAX_ITERATIONS: Hit maximum iteration limit
        TIMEOUT: Exceeded total time budget
        INFEASIBLE: Detected fundamentally unsolvable constraint set
        NO_PROGRESS: Loss not improving (stagnation)
        USER_ABORT: User cancelled the pipeline
    """

    SUCCESS = "success"
    MAX_ITERATIONS = "max_iterations"
    TIMEOUT = "timeout"
    INFEASIBLE = "infeasible"
    NO_PROGRESS = "no_progress"
    USER_ABORT = "user_abort"
    ROUTABILITY_REGRESSION = "routability_regression"
    ROUTABILITY_CONVERGED = "routability_converged"


@dataclass
class ConvergenceCriteria:
    """Define when the pipeline should stop.

    Attributes:
        max_iterations: Maximum total pipeline iterations
        max_refinement_iterations: Maximum placement-routing refinement loops
        timeout_seconds: Total time budget in seconds
        phase_timeout_seconds: Maximum time for any single phase
        max_overlap_mm2: Maximum allowed component overlap area
        max_boundary_violation_mm: Maximum allowed boundary violation
        min_routing_completion: Minimum routing completion ratio (0.0 to 1.0)
        min_manufacturing_margin_mm: Minimum manufacturing margin
        min_loss_improvement: Minimum fractional improvement to count as progress
        stagnation_epochs: Epochs without improvement before declaring stagnation
    """

    # Iteration limits
    max_iterations: int = 5
    max_refinement_iterations: int = 3

    # Time limits
    timeout_seconds: float = 600.0  # 10 minutes total
    phase_timeout_seconds: float = 120.0  # 2 minutes per phase

    # Success thresholds
    max_overlap_mm2: float = 0.01
    max_boundary_violation_mm: float = 0.01
    min_routing_completion: float = 1.0  # 100%
    min_manufacturing_margin_mm: float = 0.05

    # Progress detection
    min_loss_improvement: float = 0.001  # 0.1% improvement
    stagnation_epochs: int = 500  # Epochs without improvement


@dataclass
class ConvergenceState:
    """Track convergence during pipeline execution.

    Attributes:
        start_time: When the pipeline started
        iteration: Current iteration count
        loss_history: History of loss values
        best_loss: Best (lowest) loss seen so far
        epochs_since_improvement: Epochs since meaningful loss improvement
        terminated: Whether termination has been triggered
        termination_reason: Why termination occurred
        failure_message: Human-readable failure description
    """

    start_time: datetime

    # Iteration tracking
    iteration: int = 0

    # Loss history
    loss_history: list[float] = field(default_factory=list)
    best_loss: float = float("inf")
    epochs_since_improvement: int = 0

    # Status
    terminated: bool = False
    termination_reason: TerminationReason | None = None
    failure_message: str | None = None


class ConvergenceChecker:
    """Check if the pipeline should terminate.

    This class tracks convergence state and provides methods to check
    various termination conditions.

    Usage:
        criteria = ConvergenceCriteria(max_iterations=5)
        checker = ConvergenceChecker(criteria)

        for iteration in range(100):
            checker.increment_iteration()

            # Record loss for stagnation detection
            checker.record_loss(current_loss)

            # Check all termination conditions
            if checker.check_all():
                print(f"Terminated: {checker.state.termination_reason}")
                break

            # Check success with metrics
            metrics = {"overlap_mm2": 0.0, "routing_completion": 1.0, ...}
            if checker.check_success(metrics):
                print("Success!")
                break
    """

    def __init__(self, criteria: ConvergenceCriteria):
        """Initialize the convergence checker.

        Args:
            criteria: Convergence criteria to use for checks
        """
        self.criteria = criteria
        self.state = ConvergenceState(start_time=datetime.now())

    def check_iteration_limit(self) -> bool:
        """Check if iteration limit has been reached.

        Returns:
            True if should terminate due to iteration limit.
        """
        if self.state.iteration >= self.criteria.max_iterations:
            self.state.terminated = True
            self.state.termination_reason = TerminationReason.MAX_ITERATIONS
            return True
        return False

    def check_timeout(self) -> bool:
        """Check if timeout has been exceeded.

        Returns:
            True if should terminate due to timeout.
        """
        elapsed = self.get_elapsed_seconds()
        if elapsed >= self.criteria.timeout_seconds:
            self.state.terminated = True
            self.state.termination_reason = TerminationReason.TIMEOUT
            return True
        return False

    def get_elapsed_seconds(self) -> float:
        """Get elapsed time since pipeline start.

        Returns:
            Elapsed time in seconds.
        """
        return (datetime.now() - self.state.start_time).total_seconds()

    def record_loss(self, loss: float) -> None:
        """Record a loss value for progress tracking.

        Args:
            loss: Current loss value
        """
        self.state.loss_history.append(loss)

        # The improvement arithmetic -- `(best_loss - loss) / best_loss`
        # against `min_loss_improvement`, including the first-loss branch
        # (`best_loss == inf`) -- is the Rust kernel `record_loss`.
        new_best, improved = _rs.record_loss(
            self.state.best_loss, loss, self.criteria.min_loss_improvement
        )
        self.state.best_loss = new_best
        if improved:
            self.state.epochs_since_improvement = 0
        else:
            self.state.epochs_since_improvement += 1

    def check_stagnation(self) -> bool:
        """Check if optimization has stagnated.

        Returns:
            True if should terminate due to stagnation.
        """
        if len(self.state.loss_history) == 0:
            return False

        if self.state.epochs_since_improvement >= self.criteria.stagnation_epochs:
            self.state.terminated = True
            self.state.termination_reason = TerminationReason.NO_PROGRESS
            return True
        return False

    def check_success(self, metrics: dict[str, float]) -> bool:
        """Check if success thresholds are met.

        Args:
            metrics: Dictionary of metric values:
                - overlap_mm2: Total component overlap area
                - boundary_violation_mm: Maximum boundary violation
                - routing_completion: Routing completion ratio (0.0 to 1.0)
                - manufacturing_margin_mm: Minimum manufacturing margin

        Returns:
            True if all success thresholds are met.
        """
        # The dict defaults are resolved here (Python dict marshalling); the
        # four threshold comparisons are the Rust kernel `check_success`.
        overlap = metrics.get("overlap_mm2", float("inf"))
        boundary = metrics.get("boundary_violation_mm", float("inf"))
        routing = metrics.get("routing_completion", 0.0)
        margin = metrics.get("manufacturing_margin_mm", 0.0)
        ok = _rs.check_success(
            float(overlap),
            float(boundary),
            float(routing),
            float(margin),
            self.criteria.max_overlap_mm2,
            self.criteria.max_boundary_violation_mm,
            self.criteria.min_routing_completion,
            self.criteria.min_manufacturing_margin_mm,
        )
        if ok:
            self.state.terminated = True
            self.state.termination_reason = TerminationReason.SUCCESS
        return ok

    def check_all(self) -> bool:
        """Check all termination conditions.

        Checks in order:
        1. Already terminated (infeasible, user abort)
        2. Iteration limit
        3. Timeout
        4. Stagnation

        Returns:
            True if any termination condition is met.
        """
        # Already terminated?
        if self.state.terminated:
            return True

        # Check conditions
        if self.check_iteration_limit():
            return True
        if self.check_timeout():
            return True
        return bool(self.check_stagnation())

    def increment_iteration(self) -> None:
        """Increment the iteration count."""
        self.state.iteration += 1

    def reset(self) -> None:
        """Reset convergence state for a fresh run."""
        self.state = ConvergenceState(start_time=datetime.now())

    def mark_infeasible(self, message: str) -> None:
        """Mark the problem as infeasible.

        Args:
            message: Human-readable description of why it's infeasible
        """
        self.state.terminated = True
        self.state.termination_reason = TerminationReason.INFEASIBLE
        self.state.failure_message = message

    def mark_user_abort(self) -> None:
        """Mark the pipeline as aborted by user."""
        self.state.terminated = True
        self.state.termination_reason = TerminationReason.USER_ABORT
        self.state.failure_message = "User aborted pipeline"

    def check_routability_regression(
        self,
        routed_nets: frozenset[str],
        total_nets: int,
        previous_routed_nets: frozenset[str] | None = None,
        regression_threshold: float = 0.95,
        stall_limit: int = 2,
    ) -> bool:
        """Check for routability regression or convergence.

        Uses net-set identity (not aggregate count) to detect:
        - REGRESSION: a previously-routed net stopped routing
        - CONVERGED: identical routed nets for stall_limit consecutive iterations

        Args:
            routed_nets: Nets that routed in the current iteration.
            total_nets: Total number of nets to route.
            previous_routed_nets: Nets that routed in the previous iteration.
            regression_threshold: Routability ratio below best-so-far that
                triggers REGRESSION (default 0.95 = 5% drop).
            stall_limit: Consecutive identical-net-set iterations to declare
                CONVERGED (default 2).

        Returns:
            True if the loop should terminate (regression or convergence).
        """
        # The net-set decision and the best/stall state update are the Rust
        # kernel `check_routability_regression`; the failure-message f-string
        # rendering stays here (Python formatting). Net sets cross the
        # boundary as sorted lists; the kernel treats them as sets.
        #
        # Attribute parity: the oracle only ever READS `_stall_count` on the
        # identical-net-set path (`self.state._stall_count += 1`) and only
        # READS `_best_routability` on the non-first-call path
        # (`best_ratio = self.state._best_routability`); on the other paths
        # it only WRITES them, so unset attributes must not raise there. The
        # shim replicates both reads exactly (an unset attribute raises the
        # identical AttributeError on exactly the paths the oracle reads it),
        # and the kernel's post-call state is written back unconditionally.
        best_routed_nets = self.state._best_routed_nets  # oracle reads first
        best_routability = (
            self.state._best_routability if best_routed_nets is not None else None
        )
        if (
            previous_routed_nets is not None
            and routed_nets == previous_routed_nets
        ):
            stall_count = self.state._stall_count  # oracle reads here
        else:
            stall_count = getattr(self.state, "_stall_count", 0)
        out = _rs.check_routability_regression(
            sorted(routed_nets),
            total_nets,
            sorted(previous_routed_nets) if previous_routed_nets is not None else None,
            regression_threshold,
            stall_limit,
            sorted(best_routed_nets) if best_routed_nets is not None else None,
            best_routability,
            stall_count,
        )

        # Write back the kernel's post-call state.
        if out["best_routed"] is not None:
            self.state._best_routed_nets = frozenset(out["best_routed"])
            self.state._best_routability = out["best_ratio"]
        self.state._stall_count = out["stall_count"]

        if out["outcome"] == "regression":
            self.state.terminated = True
            self.state.termination_reason = TerminationReason.ROUTABILITY_REGRESSION
            lost = out["lost_nets"]
            self.state.failure_message = (
                f"Routability regressed: {out['current_ratio']:.3f} < "
                f"{out['threshold_product']:.3f} (threshold). "
                + (f"Lost nets: {lost}" if lost else "")
            )
            return True
        if out["outcome"] == "converged":
            self.state.terminated = True
            self.state.termination_reason = TerminationReason.ROUTABILITY_CONVERGED
            self.state.failure_message = (
                f"Routability converged: {len(routed_nets)}/{total_nets} nets "
                f"routed with identical net set for {stall_limit} iterations"
            )
            return True
        return False


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
