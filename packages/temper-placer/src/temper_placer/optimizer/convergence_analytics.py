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

import math
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
        # Ensure stagnation_epochs is valid
        if self.stagnation_epochs < 1:
            self.stagnation_epochs = 1

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

            # Guard against non-finite values
            if not math.isfinite(loss) or not math.isfinite(prev_loss):
                delta = 0.0
                improvement_rate = 0.0
            else:
                delta = loss - prev_loss

                # Compute improvement rate (positive = improvement)
                improvement_rate = -delta / abs(prev_loss) if abs(prev_loss) > 1e-10 else 0.0
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
        self._plateau_detected_this_epoch = False

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
                self._plateau_detected_this_epoch = True

            self._low_improvement_count = 0
            self._plateau_start_epoch = None

        is_stagnating = self._low_improvement_count >= self.stagnation_epochs

        # Emit plateau event when first entering stagnation
        if is_stagnating and not was_stagnating and self._plateau_start_epoch is not None:
            plateau_event = self._create_plateau_event(epoch)
            self._plateau_detected_this_epoch = True
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

        for i, _rate in enumerate(self.tracker._improvement_rate_history):
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

            if (mean_change > sensitivity * 0.5 or std_change > sensitivity) and (not transitions or i - transitions[-1] > window):
                transitions.append(i)

        return transitions


class ConvergenceConfidence(NamedTuple):
    """Convergence confidence metrics for a single epoch.

    Attributes:
        epoch: Current epoch number.
        confidence: Overall convergence confidence (0.0 to 1.0).
        improvement_confidence: Confidence from improvement rate trend.
        stability_confidence: Confidence from loss stability.
        plateau_confidence: Confidence from plateau detection.
        gradient_confidence: Confidence from gradient norms (if available).
        is_converged: Whether confidence exceeds threshold.
        reason: Human-readable explanation of confidence level.
    """

    epoch: int
    confidence: float
    improvement_confidence: float
    stability_confidence: float
    plateau_confidence: float
    gradient_confidence: float
    is_converged: bool
    reason: str


@dataclass
class ConvergenceConfidenceScorer:
    """Real-time convergence confidence estimation.

    Computes a probabilistic estimate of whether optimization has converged
    based on multiple signals:
    - Improvement rate trend (declining improvement suggests convergence)
    - Loss stability (low variance in recent losses suggests convergence)
    - Plateau detection (sustained plateaus increase confidence)
    - Gradient norms (small gradients suggest convergence, if provided)

    The scorer can be used during training to decide when to stop early.

    Attributes:
        improvement_weight: Weight for improvement rate signal (default: 0.3).
        stability_weight: Weight for loss stability signal (default: 0.3).
        plateau_weight: Weight for plateau detection signal (default: 0.25).
        gradient_weight: Weight for gradient norm signal (default: 0.15).
        stability_window: Window size for stability computation (default: 20).
        improvement_threshold: Improvement rate below this is "converged" (default: 0.001).
        stability_threshold: Variance below this is "stable" (default: 0.01).
        convergence_threshold: Confidence above this triggers is_converged (default: 0.8).

    Example:
        >>> scorer = ConvergenceConfidenceScorer()
        >>> tracker = LossImprovementTracker()
        >>>
        >>> for epoch in range(epochs):
        ...     loss = train_step(...)
        ...     metrics = tracker.update(loss)
        ...     confidence = scorer.update(tracker, grad_norm=compute_grad_norm())
        ...
        ...     if confidence.is_converged:
        ...         print(f"Converged at epoch {epoch}: {confidence.reason}")
        ...         break
    """

    # Weights for combining signals (must sum to 1.0)
    improvement_weight: float = 0.30
    stability_weight: float = 0.30
    plateau_weight: float = 0.25
    gradient_weight: float = 0.15

    # Thresholds
    stability_window: int = 20
    improvement_threshold: float = 0.001  # 0.1% improvement
    stability_threshold: float = 0.01  # Normalized variance threshold
    convergence_threshold: float = 0.8  # Confidence to declare converged

    # Internal state
    _gradient_history: list[float] = field(default_factory=list, repr=False)
    _confidence_history: list[float] = field(default_factory=list, repr=False)
    _epoch: int = field(default=0, repr=False)

    def reset(self) -> None:
        """Reset the scorer to initial state."""
        self._gradient_history.clear()
        self._confidence_history.clear()
        self._epoch = 0

    def update(
        self,
        tracker: LossImprovementTracker,
        grad_norm: float | None = None,
    ) -> ConvergenceConfidence:
        """Compute convergence confidence based on current tracker state.

        Args:
            tracker: LossImprovementTracker with current optimization state.
            grad_norm: Optional gradient norm for current epoch.

        Returns:
            ConvergenceConfidence with detailed confidence breakdown.
        """
        epoch = self._epoch
        self._epoch += 1

        # Store gradient if provided
        if grad_norm is not None:
            self._gradient_history.append(grad_norm)

        # Compute individual confidence signals
        improvement_conf = self._compute_improvement_confidence(tracker)
        stability_conf = self._compute_stability_confidence(tracker)
        plateau_conf = self._compute_plateau_confidence(tracker)
        gradient_conf = self._compute_gradient_confidence()

        # Combine signals with weights
        # Adjust weights if gradient not available
        if not self._gradient_history:
            # Redistribute gradient weight to other signals
            total_weight = self.improvement_weight + self.stability_weight + self.plateau_weight
            improvement_w = self.improvement_weight / total_weight
            stability_w = self.stability_weight / total_weight
            plateau_w = self.plateau_weight / total_weight
            gradient_w = 0.0
        else:
            improvement_w = self.improvement_weight
            stability_w = self.stability_weight
            plateau_w = self.plateau_weight
            gradient_w = self.gradient_weight

        confidence = (
            improvement_w * improvement_conf
            + stability_w * stability_conf
            + plateau_w * plateau_conf
            + gradient_w * gradient_conf
        )

        # Clamp to [0, 1]
        confidence = max(0.0, min(1.0, confidence))
        self._confidence_history.append(confidence)

        # Determine if converged
        is_converged = confidence >= self.convergence_threshold

        # Generate reason
        reason = self._generate_reason(
            confidence,
            improvement_conf,
            stability_conf,
            plateau_conf,
            gradient_conf,
            is_converged,
        )

        return ConvergenceConfidence(
            epoch=epoch,
            confidence=confidence,
            improvement_confidence=improvement_conf,
            stability_confidence=stability_conf,
            plateau_confidence=plateau_conf,
            gradient_confidence=gradient_conf,
            is_converged=is_converged,
            reason=reason,
        )

    def _compute_improvement_confidence(self, tracker: LossImprovementTracker) -> float:
        """Compute confidence from improvement rate trend.

        Low improvement rate = high confidence in convergence.
        Also considers velocity (slowing improvement = higher confidence).

        Returns:
            Confidence value from 0.0 to 1.0.
        """
        if tracker.current_epoch < 2:
            return 0.0

        rates = tracker.improvement_rate_history
        if len(rates) < 5:
            return 0.0

        # Use recent improvement rate
        recent_window = min(20, len(rates))
        recent_rates = rates[-recent_window:]
        avg_rate = sum(recent_rates) / len(recent_rates)

        # Map improvement rate to confidence
        # Below threshold = high confidence, above = low confidence
        if avg_rate <= 0:
            # Negative or zero improvement = definitely converged (or stuck)
            rate_confidence = 1.0
        elif avg_rate < self.improvement_threshold:
            # Below threshold, high confidence
            rate_confidence = 1.0 - (avg_rate / self.improvement_threshold) * 0.3
        elif avg_rate < self.improvement_threshold * 10:
            # Moderate improvement, moderate confidence
            rate_confidence = (
                0.7
                - (avg_rate - self.improvement_threshold) / (self.improvement_threshold * 9) * 0.5
            )
        else:
            # High improvement, low confidence
            rate_confidence = max(0.0, 0.2 - avg_rate * 0.1)

        # Boost confidence if velocity is negative (improvement slowing)
        velocity = tracker._compute_velocity()
        if velocity < 0:
            # Slowing down, boost confidence
            velocity_boost = min(0.2, abs(velocity) * 10)
            rate_confidence = min(1.0, rate_confidence + velocity_boost)

        return rate_confidence

    def _compute_stability_confidence(self, tracker: LossImprovementTracker) -> float:
        """Compute confidence from loss stability.

        Low variance in recent losses = high confidence.

        Returns:
            Confidence value from 0.0 to 1.0.
        """
        losses = tracker.loss_history
        if len(losses) < self.stability_window:
            return 0.0

        recent_losses = losses[-self.stability_window :]
        mean_loss = sum(recent_losses) / len(recent_losses)

        if abs(mean_loss) < 1e-10:
            # Near-zero loss, consider stable
            return 1.0

        # Compute coefficient of variation (normalized std dev)
        variance = sum((x - mean_loss) ** 2 for x in recent_losses) / len(recent_losses)
        std_dev = variance**0.5
        cv = std_dev / abs(mean_loss)

        # Map CV to confidence
        # Low CV = high stability = high confidence
        if cv < self.stability_threshold:
            return 1.0
        elif cv < self.stability_threshold * 5:
            stability_conf = 1.0 - (cv - self.stability_threshold) / (self.stability_threshold * 4)
            return float(stability_conf)
        else:
            stability_conf = 0.2 - cv * 0.1
            return stability_conf if stability_conf > 0.0 else 0.0

    def _compute_plateau_confidence(self, tracker: LossImprovementTracker) -> float:
        """Compute confidence from plateau detection.

        Currently in plateau = high confidence.
        Multiple past plateaus = moderate confidence boost.

        Returns:
            Confidence value from 0.0 to 1.0.
        """
        # Check if currently in a plateau
        current_plateau = tracker.current_plateau
        if current_plateau is not None:
            # Currently in plateau - high confidence
            # Longer plateau = higher confidence
            duration_factor = min(1.0, current_plateau.duration / 100)
            return 0.7 + 0.3 * duration_factor

        # Not currently in plateau, but check history
        past_plateaus = tracker.plateau_events
        if not past_plateaus:
            return 0.0

        # Recent plateau exit still suggests near-convergence
        last_plateau = past_plateaus[-1]
        epochs_since_plateau = tracker.current_epoch - last_plateau.end_epoch

        if epochs_since_plateau < 10:
            # Recently exited plateau
            plateau_conf = 0.6 - epochs_since_plateau * 0.03
            return plateau_conf if plateau_conf > 0.3 else 0.3
        else:
            # Long time since plateau
            plateau_conf = 0.3 - (epochs_since_plateau - 10) * 0.01
            return plateau_conf if plateau_conf > 0.0 else 0.0

    def _compute_gradient_confidence(self) -> float:
        """Compute confidence from gradient norms.

        Small gradient norms = high confidence.

        Returns:
            Confidence value from 0.0 to 1.0.
        """
        if not self._gradient_history:
            return 0.0

        # Use recent gradient history
        recent_window = min(10, len(self._gradient_history))
        recent_grads = self._gradient_history[-recent_window:]
        avg_grad = sum(recent_grads) / len(recent_grads)

        # Also check if gradients are decreasing
        if len(self._gradient_history) >= 5:
            early_grads = self._gradient_history[:5]
            early_avg = sum(early_grads) / len(early_grads)

            grad_ratio = avg_grad / early_avg if early_avg > 1e-10 else 1.0
        else:
            grad_ratio = 1.0

        # Map gradient magnitude to confidence
        # This is heuristic - actual thresholds depend on problem scale
        # Use relative decrease as primary signal
        if grad_ratio < 0.01:
            magnitude_conf = 1.0
        elif grad_ratio < 0.1:
            magnitude_conf = 0.8 + 0.2 * (0.1 - grad_ratio) / 0.09
        elif grad_ratio < 0.5:
            magnitude_conf = 0.4 + 0.4 * (0.5 - grad_ratio) / 0.4
        else:
            magnitude_conf = 0.4 * (1.0 - grad_ratio)
            return magnitude_conf if magnitude_conf > 0.0 else 0.0

        return magnitude_conf

    def _generate_reason(
        self,
        confidence: float,
        improvement_conf: float,
        stability_conf: float,
        plateau_conf: float,
        gradient_conf: float,
        is_converged: bool,
    ) -> str:
        """Generate a human-readable reason for the confidence level.

        Returns:
            Explanation string.
        """
        if is_converged:
            # Find dominant signal
            signals = [
                ("low improvement rate", improvement_conf),
                ("stable loss", stability_conf),
                ("plateau detected", plateau_conf),
                ("small gradients", gradient_conf),
            ]
            signals.sort(key=lambda x: x[1], reverse=True)

            top_reasons = [s[0] for s in signals[:2] if s[1] > 0.5]
            if top_reasons:
                return f"Converged: {', '.join(top_reasons)}"
            else:
                return "Converged: multiple weak signals"
        else:
            if confidence < 0.3:
                return "Not converged: still improving significantly"
            elif confidence < 0.5:
                return "Not converged: moderate improvement continues"
            elif confidence < 0.7:
                return "Approaching convergence: improvement slowing"
            else:
                return "Near convergence: minor adjustments continue"

    @property
    def confidence_history(self) -> list[float]:
        """Get the full confidence history."""
        return list(self._confidence_history)

    @property
    def gradient_history(self) -> list[float]:
        """Get the full gradient norm history."""
        return list(self._gradient_history)

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of convergence confidence statistics.

        Returns:
            Dictionary with summary statistics.
        """
        if not self._confidence_history:
            return {
                "total_epochs": 0,
                "final_confidence": 0.0,
                "max_confidence": 0.0,
                "avg_confidence": 0.0,
                "epochs_above_threshold": 0,
                "first_convergence_epoch": -1,
            }

        final_conf = self._confidence_history[-1]
        max_conf = max(self._confidence_history)
        avg_conf = sum(self._confidence_history) / len(self._confidence_history)

        # Count epochs above threshold
        above_threshold = sum(
            1 for c in self._confidence_history if c >= self.convergence_threshold
        )

        # Find first convergence epoch
        first_conv = -1
        for i, c in enumerate(self._confidence_history):
            if c >= self.convergence_threshold:
                first_conv = i
                break

        return {
            "total_epochs": len(self._confidence_history),
            "final_confidence": final_conf,
            "max_confidence": max_conf,
            "avg_confidence": avg_conf,
            "epochs_above_threshold": above_threshold,
            "first_convergence_epoch": first_conv,
        }
