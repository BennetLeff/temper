"""Convergence criteria and early termination for pipeline.

This module defines when the pipeline should stop iterating, including:
- Success conditions (all phases pass, routing verified, manufacturing OK)
- Failure conditions (max iterations, timeout, infeasibility, stagnation)
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


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

        # Check if this is an improvement
        if self.state.best_loss == float("inf"):
            # First loss value
            self.state.best_loss = loss
            self.state.epochs_since_improvement = 0
        else:
            # Check for meaningful improvement
            improvement = (self.state.best_loss - loss) / self.state.best_loss
            if improvement >= self.criteria.min_loss_improvement:
                self.state.best_loss = loss
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
        # Check overlap
        overlap = metrics.get("overlap_mm2", float("inf"))
        if overlap > self.criteria.max_overlap_mm2:
            return False

        # Check boundary
        boundary = metrics.get("boundary_violation_mm", float("inf"))
        if boundary > self.criteria.max_boundary_violation_mm:
            return False

        # Check routing
        routing = metrics.get("routing_completion", 0.0)
        if routing < self.criteria.min_routing_completion:
            return False

        # Check manufacturing margin
        margin = metrics.get("manufacturing_margin_mm", 0.0)
        if margin < self.criteria.min_manufacturing_margin_mm:
            return False

        # All thresholds passed
        self.state.terminated = True
        self.state.termination_reason = TerminationReason.SUCCESS
        return True

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
        if self.check_stagnation():
            return True

        return False

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
