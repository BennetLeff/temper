"""Convergence analytics for tracking optimization dynamics.

This module provides detailed tracking and analysis of loss improvement during
optimization, including:
- Epoch-over-epoch loss deltas
- Rolling averages with configurable window sizes
- Improvement velocity (rate of change of improvement rate)
- Stagnation detection

Usage:
    tracker = LossImprovementTracker(windows=[10, 50, 100])

    for epoch in range(epochs):
        loss = train_step(...)
        metrics = tracker.update(loss)

        print(f"Improvement rate: {metrics.improvement_rate:.4f}")
        print(f"Rolling avg (10): {metrics.rolling_avg_10:.4f}")
        print(f"Velocity: {metrics.velocity:.6f}")

        if metrics.is_stagnating:
            print("Warning: optimization is stagnating")
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, NamedTuple

if TYPE_CHECKING:
    from temper_placer.optimizer.train import TrainingResult


class ImprovementMetrics(NamedTuple):
    """Metrics from a single loss improvement update.

    Attributes:
        epoch: Current epoch number.
        loss: Current loss value.
        delta: Change from previous epoch (negative = improvement).
        improvement_rate: Relative improvement as fraction (positive = improvement).
        rolling_avg_10: Rolling average of deltas over last 10 epochs.
        rolling_avg_50: Rolling average of deltas over last 50 epochs.
        rolling_avg_100: Rolling average of deltas over last 100 epochs.
        velocity: Rate of change of improvement rate (acceleration).
        is_improving: Whether loss is decreasing.
        is_stagnating: Whether improvement has stalled.
        plateau_event: PlateauEvent if a plateau was just detected, else None.
    """

    epoch: int
    loss: float
    delta: float
    improvement_rate: float
    rolling_avg_10: float
    rolling_avg_50: float
    rolling_avg_100: float
    velocity: float
    is_improving: bool
    is_stagnating: bool
    plateau_event: PlateauEvent | None = None


@dataclass
class PlateauEvent:
    """Event emitted when a plateau is detected.

    A plateau occurs when the improvement rate falls below the threshold
    for a configurable number of consecutive epochs.

    Attributes:
        start_epoch: First epoch of the plateau.
        end_epoch: Last epoch of the plateau (current epoch when detected).
        duration: Number of epochs in the plateau.
        avg_loss: Average loss during the plateau.
        min_loss: Minimum loss during the plateau.
        avg_improvement_rate: Average improvement rate during plateau.
    """

    start_epoch: int
    end_epoch: int
    duration: int
    avg_loss: float
    min_loss: float
    avg_improvement_rate: float

    def __repr__(self) -> str:
        return (
            f"PlateauEvent(epochs={self.start_epoch}-{self.end_epoch}, "
            f"duration={self.duration}, avg_loss={self.avg_loss:.4f})"
        )


@dataclass
class LossImprovementTracker:
    """Track and analyze loss improvement dynamics during optimization.

    This class maintains a history of loss values and computes various
    improvement metrics including rolling averages and velocity.

    Attributes:
        windows: List of window sizes for rolling averages.
        stagnation_threshold: Minimum improvement rate to not be considered stagnating.
        stagnation_epochs: Number of epochs of low improvement before stagnation.
        velocity_window: Window size for computing velocity.

    Example:
        >>> tracker = LossImprovementTracker()
        >>> tracker.update(100.0)  # Initial loss
        >>> metrics = tracker.update(95.0)  # 5% improvement
        >>> print(f"Improvement: {metrics.improvement_rate:.2%}")
        Improvement: 5.00%
    """

    windows: list[int] = field(default_factory=lambda: [10, 50, 100])
    stagnation_threshold: float = 0.0001  # 0.01% improvement
    stagnation_epochs: int = 50
    velocity_window: int = 10

    # Internal state
    _loss_history: list[float] = field(default_factory=list, repr=False)
    _delta_history: list[float] = field(default_factory=list, repr=False)
    _improvement_rate_history: list[float] = field(default_factory=list, repr=False)
    _epoch: int = field(default=0, repr=False)
    _low_improvement_count: int = field(default=0, repr=False)
    _plateau_start_epoch: int | None = field(default=None, repr=False)
    _plateau_events: list[PlateauEvent] = field(default_factory=list, repr=False)
    _plateau_detected_this_epoch: bool = field(default=False, repr=False)

    def __post_init__(self) -> None:
        """Initialize internal buffers."""
        # Pre-allocate deques for efficient rolling window computation
        self._delta_buffers: dict[int, deque[float]] = {w: deque(maxlen=w) for w in self.windows}
        self._improvement_rate_buffer: deque[float] = deque(maxlen=self.velocity_window)

    def reset(self) -> None:
        """Reset the tracker to initial state."""
        self._loss_history.clear()
        self._delta_history.clear()
        self._improvement_rate_history.clear()
        self._epoch = 0
        self._low_improvement_count = 0
        self._plateau_start_epoch = None
        self._plateau_events.clear()
        self._plateau_detected_this_epoch = False

        for buffer in self._delta_buffers.values():
            buffer.clear()
        self._improvement_rate_buffer.clear()

    def update(self, loss: float) -> ImprovementMetrics:
        """Update tracker with new loss value and compute metrics.

        Args:
            loss: Current epoch's loss value.

        Returns:
            ImprovementMetrics with computed analytics.
        """
        epoch = self._epoch
        self._epoch += 1

        # Store loss
        self._loss_history.append(loss)

        # Compute delta (negative = improvement)
        if len(self._loss_history) >= 2:
            prev_loss = self._loss_history[-2]
            delta = loss - prev_loss

            # Compute improvement rate (positive = improvement)
            if abs(prev_loss) > 1e-10:
                improvement_rate = -delta / abs(prev_loss)
            else:
                improvement_rate = 0.0
        else:
            # First epoch - no delta yet
            delta = 0.0
            improvement_rate = 0.0

        # Store delta and improvement rate
        self._delta_history.append(delta)
        self._improvement_rate_history.append(improvement_rate)

        # Update delta buffers for rolling averages
        for buffer in self._delta_buffers.values():
            buffer.append(delta)

        # Update improvement rate buffer for velocity
        self._improvement_rate_buffer.append(improvement_rate)

        # Compute rolling averages
        rolling_avgs = {}
        for window in self.windows:
            buffer = self._delta_buffers[window]
            if len(buffer) > 0:
                rolling_avgs[window] = sum(buffer) / len(buffer)
            else:
                rolling_avgs[window] = 0.0

        # Compute velocity (rate of change of improvement rate)
        velocity = self._compute_velocity()

        # Determine if improving
        is_improving = delta < 0

        # Determine if stagnating and track plateau events
        plateau_event = None
        was_stagnating = self._low_improvement_count >= self.stagnation_epochs

        if improvement_rate < self.stagnation_threshold:
            self._low_improvement_count += 1

            # Track plateau start
            if self._low_improvement_count == 1:
                self._plateau_start_epoch = epoch
        else:
            # Exiting a plateau - emit event if we were in one
            if was_stagnating and self._plateau_start_epoch is not None:
                plateau_event = self._create_plateau_event(epoch - 1)
                self._plateau_events.append(plateau_event)

            self._low_improvement_count = 0
            self._plateau_start_epoch = None

        is_stagnating = self._low_improvement_count >= self.stagnation_epochs

        # Emit plateau event when first entering stagnation
        if is_stagnating and not was_stagnating and self._plateau_start_epoch is not None:
            plateau_event = self._create_plateau_event(epoch)
            # Don't add to events yet - still ongoing

        return ImprovementMetrics(
            epoch=epoch,
            loss=loss,
            delta=delta,
            improvement_rate=improvement_rate,
            rolling_avg_10=rolling_avgs.get(10, 0.0),
            rolling_avg_50=rolling_avgs.get(50, 0.0),
            rolling_avg_100=rolling_avgs.get(100, 0.0),
            velocity=velocity,
            is_improving=is_improving,
            is_stagnating=is_stagnating,
            plateau_event=plateau_event,
        )

    def _create_plateau_event(self, end_epoch: int) -> PlateauEvent:
        """Create a PlateauEvent for the current/recent plateau.

        Args:
            end_epoch: The last epoch of the plateau.

        Returns:
            PlateauEvent with computed statistics.
        """
        start = self._plateau_start_epoch or 0
        duration = end_epoch - start + 1

        # Get losses and rates during plateau
        plateau_losses = self._loss_history[start : end_epoch + 1]
        plateau_rates = self._improvement_rate_history[start : end_epoch + 1]

        avg_loss = sum(plateau_losses) / len(plateau_losses) if plateau_losses else 0.0
        min_loss = min(plateau_losses) if plateau_losses else 0.0
        avg_rate = sum(plateau_rates) / len(plateau_rates) if plateau_rates else 0.0

        return PlateauEvent(
            start_epoch=start,
            end_epoch=end_epoch,
            duration=duration,
            avg_loss=avg_loss,
            min_loss=min_loss,
            avg_improvement_rate=avg_rate,
        )

    def _compute_velocity(self) -> float:
        """Compute velocity (acceleration) of improvement.

        Velocity is the rate of change of improvement rate. Positive velocity
        means improvement is accelerating, negative means it's decelerating.

        Returns:
            Velocity as change in improvement rate per epoch.
        """
        buffer = self._improvement_rate_buffer
        if len(buffer) < 2:
            return 0.0

        # Use linear regression slope for more stable velocity estimate
        # y = improvement_rate, x = epoch index in window
        n = len(buffer)
        x_mean = (n - 1) / 2.0
        y_mean = sum(buffer) / n

        numerator = 0.0
        denominator = 0.0

        for i, y in enumerate(buffer):
            x_diff = i - x_mean
            numerator += x_diff * (y - y_mean)
            denominator += x_diff * x_diff

        if abs(denominator) < 1e-10:
            return 0.0

        return numerator / denominator

    @property
    def loss_history(self) -> list[float]:
        """Get the full loss history."""
        return list(self._loss_history)

    @property
    def delta_history(self) -> list[float]:
        """Get the full delta history."""
        return list(self._delta_history)

    @property
    def improvement_rate_history(self) -> list[float]:
        """Get the full improvement rate history."""
        return list(self._improvement_rate_history)

    @property
    def current_epoch(self) -> int:
        """Get the current epoch count."""
        return self._epoch

    @property
    def best_loss(self) -> float:
        """Get the best (minimum) loss seen so far."""
        if not self._loss_history:
            return float("inf")
        return min(self._loss_history)

    @property
    def best_epoch(self) -> int:
        """Get the epoch where best loss was achieved."""
        if not self._loss_history:
            return -1
        return self._loss_history.index(min(self._loss_history))

    @property
    def plateau_events(self) -> list[PlateauEvent]:
        """Get all detected plateau events."""
        return list(self._plateau_events)

    @property
    def current_plateau(self) -> PlateauEvent | None:
        """Get the current ongoing plateau, if any."""
        if (
            self._low_improvement_count >= self.stagnation_epochs
            and self._plateau_start_epoch is not None
        ):
            return self._create_plateau_event(self._epoch - 1)
        return None

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of convergence statistics.

        Returns:
            Dictionary with summary statistics:
            - total_epochs: Number of epochs tracked
            - initial_loss: Loss at epoch 0
            - final_loss: Loss at last epoch
            - best_loss: Minimum loss achieved
            - best_epoch: Epoch of best loss
            - total_improvement: Final - Initial (negative = good)
            - total_improvement_rate: Total improvement as fraction
            - avg_improvement_rate: Mean improvement rate per epoch
            - final_velocity: Velocity at last epoch
            - n_plateaus: Number of plateau events detected
            - total_plateau_epochs: Total epochs spent in plateaus
            - plateaus: List of plateau event dictionaries
        """
        if not self._loss_history:
            return {
                "total_epochs": 0,
                "initial_loss": float("nan"),
                "final_loss": float("nan"),
                "best_loss": float("nan"),
                "best_epoch": -1,
                "total_improvement": 0.0,
                "total_improvement_rate": 0.0,
                "avg_improvement_rate": 0.0,
                "final_velocity": 0.0,
                "n_plateaus": 0,
                "total_plateau_epochs": 0,
                "plateaus": [],
            }

        initial_loss = self._loss_history[0]
        final_loss = self._loss_history[-1]
        best_loss = min(self._loss_history)
        best_epoch = self._loss_history.index(best_loss)

        total_improvement = initial_loss - final_loss
        total_improvement_rate = (
            total_improvement / abs(initial_loss) if abs(initial_loss) > 1e-10 else 0.0
        )
        avg_improvement_rate = (
            sum(self._improvement_rate_history) / len(self._improvement_rate_history)
            if self._improvement_rate_history
            else 0.0
        )

        # Plateau statistics
        plateau_dicts = [
            {
                "start_epoch": p.start_epoch,
                "end_epoch": p.end_epoch,
                "duration": p.duration,
                "avg_loss": p.avg_loss,
                "min_loss": p.min_loss,
                "avg_improvement_rate": p.avg_improvement_rate,
            }
            for p in self._plateau_events
        ]
        total_plateau_epochs = sum(p.duration for p in self._plateau_events)

        return {
            "total_epochs": len(self._loss_history),
            "initial_loss": initial_loss,
            "final_loss": final_loss,
            "best_loss": best_loss,
            "best_epoch": best_epoch,
            "total_improvement": total_improvement,
            "total_improvement_rate": total_improvement_rate,
            "avg_improvement_rate": avg_improvement_rate,
            "final_velocity": self._compute_velocity(),
            "n_plateaus": len(self._plateau_events),
            "total_plateau_epochs": total_plateau_epochs,
            "plateaus": plateau_dicts,
        }


@dataclass
class ConvergenceAnalyzer:
    """Analyze convergence patterns in training history.

    This class provides post-hoc analysis of training metrics to identify
    convergence patterns, phase transitions, and optimization quality.

    Example:
        >>> from temper_placer.optimizer.train import TrainingResult
        >>> analyzer = ConvergenceAnalyzer.from_training_result(result)
        >>> print(f"Converged at epoch: {analyzer.convergence_epoch}")
        >>> print(f"Convergence quality: {analyzer.quality_score:.2f}")
    """

    tracker: LossImprovementTracker

    @classmethod
    def from_loss_history(cls, losses: list[float]) -> ConvergenceAnalyzer:
        """Create analyzer from a list of loss values.

        Args:
            losses: List of loss values, one per epoch.

        Returns:
            ConvergenceAnalyzer with populated tracker.
        """
        tracker = LossImprovementTracker()
        for loss in losses:
            tracker.update(loss)
        return cls(tracker=tracker)

    @classmethod
    def from_training_result(cls, result: TrainingResult) -> ConvergenceAnalyzer:
        """Create analyzer from a TrainingResult.

        Args:
            result: TrainingResult from train() or train_multiphase().

        Returns:
            ConvergenceAnalyzer with populated tracker.
        """
        losses = [m.loss for m in result.history]
        return cls.from_loss_history(losses)

    @property
    def convergence_epoch(self) -> int:
        """Estimate the epoch where convergence occurred.

        Uses a combination of:
        1. When improvement rate dropped below threshold
        2. When velocity approached zero
        3. When rolling average stabilized

        Returns:
            Estimated convergence epoch, or -1 if not converged.
        """
        if len(self.tracker._improvement_rate_history) < 20:
            return -1

        # Find first epoch where rolling avg and velocity are both near zero
        threshold = 0.001  # 0.1% improvement

        for i, rate in enumerate(self.tracker._improvement_rate_history):
            if i < 10:
                continue

            # Check if improvement has stabilized
            recent_rates = self.tracker._improvement_rate_history[max(0, i - 10) : i + 1]
            avg_rate = sum(recent_rates) / len(recent_rates)

            if avg_rate < threshold and avg_rate > -threshold:
                return i

        return -1

    @property
    def quality_score(self) -> float:
        """Compute a convergence quality score.

        Score is based on:
        - How much the loss improved (higher = better)
        - How smooth the convergence was (lower variance = better)
        - Whether the optimizer found a stable minimum

        Returns:
            Quality score from 0.0 (poor) to 1.0 (excellent).
        """
        summary = self.tracker.get_summary()

        total_epochs = int(summary["total_epochs"])
        if total_epochs < 10:
            return 0.0

        # Component 1: Total improvement (0 to 0.4)
        improvement_rate = float(summary["total_improvement_rate"])
        improvement_score = min(0.4, improvement_rate * 0.5)  # Cap at 0.4, 80% improvement = max

        # Component 2: Smoothness (0 to 0.3)
        # Lower variance in improvement rate = smoother
        rates = self.tracker._improvement_rate_history
        if len(rates) > 1:
            mean_rate = sum(rates) / len(rates)
            variance = sum((r - mean_rate) ** 2 for r in rates) / len(rates)
            # Map variance to score: low variance = high score
            smoothness_score = 0.3 * max(0, 1.0 - min(1.0, variance * 100))
        else:
            smoothness_score = 0.0

        # Component 3: Stability at end (0 to 0.3)
        # Check if the final epochs are stable
        if len(rates) >= 10:
            final_rates = rates[-10:]
            final_variance = sum((r - sum(final_rates) / 10) ** 2 for r in final_rates) / 10
            stability_score = 0.3 * max(0, 1.0 - min(1.0, final_variance * 1000))
        else:
            stability_score = 0.0

        return min(1.0, improvement_score + smoothness_score + stability_score)

    def find_phase_transitions(self, sensitivity: float = 2.0) -> list[int]:
        """Find epochs where the optimization dynamics changed significantly.

        This detects curriculum phase transitions, learning rate changes,
        or other regime changes in the optimization.

        Args:
            sensitivity: How sensitive to changes (higher = more transitions detected).

        Returns:
            List of epoch indices where transitions occurred.
        """
        if len(self.tracker._delta_history) < 20:
            return []

        transitions: list[int] = []
        deltas = self.tracker._delta_history

        # Compute local statistics in sliding windows
        window = 10
        for i in range(window, len(deltas) - window):
            # Compare statistics before and after this point
            before = deltas[i - window : i]
            after = deltas[i : i + window]

            mean_before = sum(before) / window
            mean_after = sum(after) / window

            std_before = (sum((x - mean_before) ** 2 for x in before) / window) ** 0.5
            std_after = (sum((x - mean_after) ** 2 for x in after) / window) ** 0.5

            # Detect significant change in mean or variance
            mean_change = abs(mean_after - mean_before) / (abs(mean_before) + 1e-10)
            std_change = abs(std_after - std_before) / (std_before + 1e-10)

            if mean_change > sensitivity * 0.5 or std_change > sensitivity:
                # Check if we haven't just recorded a nearby transition
                if not transitions or i - transitions[-1] > window:
                    transitions.append(i)

        return transitions
