"""Decision logger for optimizer integration.

This module provides the DecisionLogger class which hooks into the optimizer
and heuristics pipeline to automatically capture placement decisions.

The logger provides:
- Position and rotation logging with full context
- Heuristic decision logging
- Constraint application logging
- Interval-based logging control for training loops
- Significant change detection to reduce noise
- Context managers for phase/epoch scoping

Wave 4, Phase 5: ``should_log`` (Python-modulo interval gating),
``significant_change`` (Euclidean distance) and the decision-construction
logic of the four ``log_*`` methods now live in the ``temper-io-types`` Rust
crate (``explain.rs``); this module is a delegation shim. Enable/disable
state, the context managers and ``trace.add`` stay Python runtime semantics.

Example:
    >>> logger = DecisionLogger()
    >>> logger.set_phase(DecisionPhase.GEOMETRIC)
    >>> logger.set_epoch(100)
    >>> logger.log_position("C1", (10.0, 20.0), reason="Gradient update")
    >>> print(logger.trace.why("C1"))
    C1 is at (10.0, 20.0) because: Gradient update
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING

import temper_io_types as _rust

from temper_placer.explainability.decision import (
    Alternative,
    Decision,
    DecisionPhase,
    DecisionTrace,
    DecisionType,
)

if TYPE_CHECKING:
    pass


class DecisionLogger:
    """Logger that captures placement decisions for explainability.

    The DecisionLogger hooks into the optimizer and heuristics pipeline to
    automatically record every decision with full context. It provides:

    - Enable/disable control for conditional logging
    - Phase and epoch tracking for decision context
    - Helper methods for interval-based logging and change detection
    - Context managers for scoped phase/epoch settings

    Attributes:
        current_phase: Current pipeline phase (SEMANTIC, TOPOLOGICAL, etc.)
        current_epoch: Current optimizer epoch (None if not in training)
        current_iteration: Current iteration within epoch (optional)

    Example:
        >>> logger = DecisionLogger()
        >>> logger.set_phase(DecisionPhase.GEOMETRIC)
        >>> for epoch in range(1000):
        ...     logger.set_epoch(epoch)
        ...     if logger.should_log(epoch, interval=100):
        ...         for comp, pos in positions.items():
        ...             if logger.significant_change(old_pos[comp], pos):
        ...                 logger.log_position(comp, pos, previous=old_pos[comp])
    """

    def __init__(self, trace: DecisionTrace | None = None) -> None:
        """Initialize the decision logger.

        Args:
            trace: Optional existing trace to append to. If None, creates
                   a new DecisionTrace.
        """
        self.trace = trace if trace is not None else DecisionTrace()
        self._enabled = True
        self.current_phase = DecisionPhase.GEOMETRIC
        self.current_epoch: int | None = None
        self.current_iteration: int | None = None

    def enable(self) -> None:
        """Enable logging."""
        self._enabled = True

    def disable(self) -> None:
        """Disable logging (all log_* methods become no-ops)."""
        self._enabled = False

    def is_enabled(self) -> bool:
        """Check if logging is enabled."""
        return self._enabled

    def set_phase(self, phase: DecisionPhase) -> None:
        """Set the current pipeline phase.

        Args:
            phase: The phase to set (SEMANTIC, TOPOLOGICAL, GEOMETRIC, etc.)
        """
        self.current_phase = phase

    def set_epoch(self, epoch: int) -> None:
        """Set the current optimizer epoch.

        Args:
            epoch: The epoch number (0-indexed)
        """
        self.current_epoch = epoch

    def set_iteration(self, iteration: int) -> None:
        """Set the current iteration within an epoch.

        Args:
            iteration: The iteration number
        """
        self.current_iteration = iteration

    @contextmanager
    def phase(self, phase: DecisionPhase) -> Generator[None, None, None]:
        """Context manager for temporarily setting the phase.

        Args:
            phase: The phase to set within the context

        Example:
            >>> with logger.phase(DecisionPhase.ROUTING):
            ...     logger.log_position("C1", (10.0, 20.0))
        """
        old_phase = self.current_phase
        self.current_phase = phase
        try:
            yield
        finally:
            self.current_phase = old_phase

    @contextmanager
    def epoch(self, epoch: int) -> Generator[None, None, None]:
        """Context manager for temporarily setting the epoch.

        Args:
            epoch: The epoch to set within the context

        Example:
            >>> with logger.epoch(500):
            ...     logger.log_position("C1", (10.0, 20.0))
        """
        old_epoch = self.current_epoch
        self.current_epoch = epoch
        try:
            yield
        finally:
            self.current_epoch = old_epoch

    def log_position(
        self,
        component: str,
        position: tuple[float, float],
        previous: tuple[float, float] | None = None,
        reason: str = "",
        constraint_refs: list[str] | None = None,
        alternatives: list[Alternative] | None = None,
        loss_delta: float | None = None,
    ) -> None:
        """Log a position decision.

        Args:
            component: Component reference designator (e.g., "C1", "Q1")
            position: New position as (x, y) tuple in mm
            previous: Previous position if this is an update (None for initial)
            reason: Human-readable explanation for the placement
            constraint_refs: List of constraint IDs that influenced this decision
            alternatives: List of rejected alternatives
            loss_delta: Change in loss due to this placement
        """
        if not self._enabled:
            return

        payload = _rust.explain_log_position(
            self.current_phase.value, component, position, previous, reason,
            constraint_refs or [], alternatives or [], loss_delta,
            self.current_epoch, self.current_iteration,
        )
        decision = _decision_from_payload(payload)
        self.trace.add(decision)

    def log_rotation(
        self,
        component: str,
        rotation: int,
        previous: int | None = None,
        reason: str = "",
    ) -> None:
        """Log a rotation decision.

        Args:
            component: Component reference designator
            rotation: New rotation index (0=0°, 1=90°, 2=180°, 3=270°)
            previous: Previous rotation if this is an update
            reason: Human-readable explanation
        """
        if not self._enabled:
            return

        payload = _rust.explain_log_rotation(
            self.current_phase.value, component, rotation, previous, reason,
            self.current_epoch, self.current_iteration,
        )
        decision = _decision_from_payload(payload)
        self.trace.add(decision)

    def log_heuristic(
        self,
        heuristic_name: str,
        component: str,
        position: tuple[float, float],
        reason: str = "",
        confidence: float = 1.0,
    ) -> None:
        """Log a heuristic placement decision.

        This is used when a heuristic places a component during the
        initialization phase (before gradient optimization).

        Args:
            heuristic_name: Name of the heuristic (e.g., "thermal_edge")
            component: Component reference designator
            position: Placed position as (x, y) tuple
            reason: Custom reason (if empty, uses heuristic name)
            confidence: Confidence score (0.0-1.0) for the placement
        """
        if not self._enabled:
            return

        payload = _rust.explain_log_heuristic(
            heuristic_name, component, position, reason, confidence,
            self.current_epoch, self.current_iteration,
        )
        decision = _decision_from_payload(payload)
        self.trace.add(decision)

    def log_constraint_application(
        self,
        constraint_id: str,
        affected_components: list[str],
        action: str,
        reason: str = "",
    ) -> None:
        """Log a constraint application.

        Args:
            constraint_id: The constraint identifier (e.g., "thermal.edge")
            affected_components: List of components affected by this constraint
            action: What action was taken (e.g., "moved_to_edge", "enforced_spacing")
            reason: Human-readable explanation (if empty, generates from action)
        """
        if not self._enabled:
            return

        payload = _rust.explain_log_constraint(
            self.current_phase.value, constraint_id, affected_components, action, reason,
            self.current_epoch, self.current_iteration,
        )
        decision = _decision_from_payload(payload)
        self.trace.add(decision)

    def should_log(
        self,
        epoch: int,
        interval: int = 100,
        is_final: bool = False,
    ) -> bool:
        """Check if logging should occur at this epoch.

        This is a helper for interval-based logging during training.
        Returns True at epoch 0, at every interval boundary, and at
        the final epoch.

        Args:
            epoch: Current epoch number
            interval: Logging interval (e.g., 100 = log every 100 epochs)
            is_final: Whether this is the final epoch

        Returns:
            True if logging should occur at this epoch
        """
        return _rust.explain_should_log(epoch, interval, is_final)

    def significant_change(
        self,
        old: tuple[float, float],
        new: tuple[float, float],
        threshold: float = 0.5,
    ) -> bool:
        """Check if a position change is significant enough to log.

        Uses Euclidean distance to determine if a component has moved
        enough to warrant logging.

        Args:
            old: Previous position (x, y)
            new: New position (x, y)
            threshold: Minimum distance in mm to be considered significant

        Returns:
            True if the movement is >= threshold
        """
        return _rust.explain_significant_change(old, new, threshold)


def _decision_from_payload(payload: dict) -> Decision:
    """Build a Decision from the Rust decision-construction payload.

    Enum construction (``DecisionType(value)`` / ``DecisionPhase(value)``)
    stays Python stdlib per the established rulings; the payload fields
    (type selection, reason generation, defaults) are computed by Rust.
    """
    return Decision(
        decision_type=DecisionType(payload["decision_type"]),
        phase=DecisionPhase(payload["phase"]),
        subject=payload["subject"],
        value=payload["value"],
        previous_value=payload["previous_value"],
        reason=payload["reason"],
        constraint_refs=payload["constraint_refs"],
        loss_contribution=payload["loss_contribution"],
        alternatives=payload["alternatives"],
        epoch=payload["epoch"],
        iteration=payload["iteration"],
    )
