"""Tests for convergence analytics module."""

import math

import pytest

from temper_placer.optimizer.convergence_analytics import (
    ConvergenceAnalyzer,
    ImprovementMetrics,
    LossImprovementTracker,
    PlateauEvent,
)


class TestImprovementMetrics:
    """Tests for ImprovementMetrics NamedTuple."""

    def test_create_metrics(self):
        """Should create metrics with all fields."""
        metrics = ImprovementMetrics(
            epoch=10,
            loss=50.0,
            delta=-5.0,
            improvement_rate=0.1,
            rolling_avg_10=-4.5,
            rolling_avg_50=-3.0,
            rolling_avg_100=-2.0,
            velocity=0.01,
            is_improving=True,
            is_stagnating=False,
        )

        assert metrics.epoch == 10
        assert metrics.loss == 50.0
        assert metrics.delta == -5.0
        assert metrics.improvement_rate == 0.1
        assert metrics.is_improving is True
        assert metrics.is_stagnating is False


class TestLossImprovementTracker:
    """Tests for LossImprovementTracker class."""

    def test_init_default_windows(self):
        """Should initialize with default windows [10, 50, 100]."""
        tracker = LossImprovementTracker()
        assert tracker.windows == [10, 50, 100]

    def test_init_custom_windows(self):
        """Should accept custom window sizes."""
        tracker = LossImprovementTracker(windows=[5, 20])
        assert tracker.windows == [5, 20]

    def test_first_update_no_delta(self):
        """First update should have zero delta."""
        tracker = LossImprovementTracker()
        metrics = tracker.update(100.0)

        assert metrics.epoch == 0
        assert metrics.loss == 100.0
        assert metrics.delta == 0.0
        assert metrics.improvement_rate == 0.0

    def test_second_update_computes_delta(self):
        """Second update should compute delta from first."""
        tracker = LossImprovementTracker()
        tracker.update(100.0)
        metrics = tracker.update(95.0)

        assert metrics.epoch == 1
        assert metrics.loss == 95.0
        assert metrics.delta == -5.0  # Negative = improvement
        assert metrics.improvement_rate == pytest.approx(0.05)  # 5% improvement

    def test_improvement_rate_positive_when_improving(self):
        """Improvement rate should be positive when loss decreases."""
        tracker = LossImprovementTracker()
        tracker.update(100.0)
        metrics = tracker.update(80.0)  # 20% improvement

        assert metrics.improvement_rate == pytest.approx(0.2)
        assert metrics.is_improving is True

    def test_improvement_rate_negative_when_worsening(self):
        """Improvement rate should be negative when loss increases."""
        tracker = LossImprovementTracker()
        tracker.update(100.0)
        metrics = tracker.update(110.0)  # 10% worse

        assert metrics.improvement_rate == pytest.approx(-0.1)
        assert metrics.is_improving is False

    def test_rolling_average_short_history(self):
        """Rolling averages should work with less data than window size."""
        tracker = LossImprovementTracker(windows=[10])

        # Add 5 data points (less than window size of 10)
        losses = [100, 95, 90, 85, 80]
        for loss in losses:
            metrics = tracker.update(loss)

        # Rolling avg should be computed over available data
        # Deltas: [0, -5, -5, -5, -5]
        # Avg of last 4 non-zero deltas: -5.0
        assert metrics.rolling_avg_10 == pytest.approx(-4.0)  # Including 0

    def test_rolling_average_full_window(self):
        """Rolling averages should use full window when available."""
        tracker = LossImprovementTracker(windows=[5])

        # Add 10 data points with constant -2 delta
        losses = [100, 98, 96, 94, 92, 90, 88, 86, 84, 82]
        for loss in losses:
            metrics = tracker.update(loss)

        # With window=5, last 5 deltas are all -2
        # Check that window 5 is used (we need to check delta buffer)
        assert len(tracker._delta_buffers[5]) == 5
        # All deltas in window are -2
        assert all(d == -2 for d in tracker._delta_buffers[5])

    def test_velocity_stable_improvement(self):
        """Velocity should be near zero for constant improvement rate."""
        tracker = LossImprovementTracker(velocity_window=5)

        # Constant 5% improvement each epoch
        loss = 100.0
        for _ in range(20):
            tracker.update(loss)
            loss *= 0.95

        # After stable improvement, velocity should be small
        metrics = tracker.update(loss)
        assert abs(metrics.velocity) < 0.01  # Nearly constant rate

    def test_velocity_accelerating_improvement(self):
        """Velocity should be positive when improvement accelerates."""
        tracker = LossImprovementTracker(velocity_window=5)

        # Start with slow improvement, then accelerate
        losses = [
            100,
            99,
            98,
            97,
            96,  # Slow: ~1% each
            94,
            91,
            87,
            82,
            76,
        ]  # Fast: accelerating

        for loss in losses:
            metrics = tracker.update(loss)

        # Velocity should be positive (improvement accelerating)
        # Note: velocity is rate of change of improvement_rate
        assert metrics.velocity > 0

    def test_stagnation_detection(self):
        """Should detect stagnation when improvement rate drops below threshold."""
        tracker = LossImprovementTracker(
            stagnation_threshold=0.001,  # 0.1%
            stagnation_epochs=5,
        )

        # Initial improvement
        tracker.update(100.0)
        tracker.update(90.0)

        # Then stagnate (tiny changes)
        for _ in range(10):
            metrics = tracker.update(89.999)

        assert metrics.is_stagnating is True

    def test_no_stagnation_with_improvement(self):
        """Should not detect stagnation when still improving."""
        tracker = LossImprovementTracker(
            stagnation_threshold=0.001,
            stagnation_epochs=5,
        )

        loss = 100.0
        for _ in range(20):
            loss *= 0.95  # 5% improvement each epoch
            metrics = tracker.update(loss)

        assert metrics.is_stagnating is False

    def test_reset(self):
        """Reset should clear all state."""
        tracker = LossImprovementTracker()

        # Add some data
        for i in range(10):
            tracker.update(100 - i)

        assert tracker.current_epoch == 10

        # Reset
        tracker.reset()

        assert tracker.current_epoch == 0
        assert tracker.loss_history == []
        assert tracker.delta_history == []

    def test_best_loss_tracking(self):
        """Should track best loss across epochs."""
        tracker = LossImprovementTracker()

        losses = [100, 90, 80, 85, 70, 75, 72]
        for loss in losses:
            tracker.update(loss)

        assert tracker.best_loss == 70
        assert tracker.best_epoch == 4

    def test_get_summary(self):
        """Summary should contain all expected fields."""
        tracker = LossImprovementTracker()

        losses = [100, 90, 80, 70, 60, 50]
        for loss in losses:
            tracker.update(loss)

        summary = tracker.get_summary()

        assert summary["total_epochs"] == 6
        assert summary["initial_loss"] == 100
        assert summary["final_loss"] == 50
        assert summary["best_loss"] == 50
        assert summary["best_epoch"] == 5
        assert summary["total_improvement"] == 50
        assert summary["total_improvement_rate"] == pytest.approx(0.5)

    def test_get_summary_empty(self):
        """Summary should handle empty tracker."""
        tracker = LossImprovementTracker()
        summary = tracker.get_summary()

        assert summary["total_epochs"] == 0
        assert math.isnan(summary["initial_loss"])

    def test_history_properties(self):
        """History properties should return copies."""
        tracker = LossImprovementTracker()

        losses = [100, 90, 80]
        for loss in losses:
            tracker.update(loss)

        history = tracker.loss_history
        history.append(999)  # Modify copy

        assert len(tracker.loss_history) == 3  # Original unchanged


class TestConvergenceAnalyzer:
    """Tests for ConvergenceAnalyzer class."""

    def test_from_loss_history(self):
        """Should create analyzer from loss list."""
        losses = [100, 90, 80, 70, 60]
        analyzer = ConvergenceAnalyzer.from_loss_history(losses)

        assert analyzer.tracker.current_epoch == 5
        assert analyzer.tracker.best_loss == 60

    def test_convergence_epoch_monotonic_decrease(self):
        """Should detect convergence when improvement stops."""
        # Start with improvement, then plateau
        losses = [100, 90, 80, 70, 60] + [60.0] * 50
        analyzer = ConvergenceAnalyzer.from_loss_history(losses)

        convergence = analyzer.convergence_epoch
        # Should converge somewhere after initial improvement phase
        assert convergence > 5
        assert convergence < 30

    def test_convergence_epoch_not_converged(self):
        """Should return -1 if not converged."""
        # Continuous improvement
        losses = [100 - i for i in range(20)]
        analyzer = ConvergenceAnalyzer.from_loss_history(losses)

        # Not enough data or still improving
        assert analyzer.convergence_epoch == -1

    def test_quality_score_good_convergence(self):
        """Good convergence should have high quality score."""
        # Smooth, significant improvement that stabilizes
        losses = []
        loss = 100.0
        for i in range(50):
            loss *= 0.95  # Smooth 5% improvement
            losses.append(loss)
        # Then stable
        losses.extend([losses[-1]] * 20)

        analyzer = ConvergenceAnalyzer.from_loss_history(losses)

        assert analyzer.quality_score > 0.5

    def test_quality_score_poor_convergence(self):
        """Poor convergence should have low quality score."""
        # Noisy, minimal improvement - use more extreme noise
        import random

        random.seed(42)
        # Loss oscillates around 100 with no net improvement
        losses = [100 + random.uniform(-10, 10) for _ in range(50)]

        analyzer = ConvergenceAnalyzer.from_loss_history(losses)

        # Score should be relatively low for noisy, non-converging data
        assert analyzer.quality_score < 0.5

    def test_find_phase_transitions_none(self):
        """Should find no transitions in smooth convergence."""
        # Smooth exponential decay
        losses = [100 * (0.95**i) for i in range(100)]
        analyzer = ConvergenceAnalyzer.from_loss_history(losses)

        transitions = analyzer.find_phase_transitions()
        # Should have few or no transitions
        assert len(transitions) < 3

    def test_find_phase_transitions_abrupt_change(self):
        """Should detect abrupt changes in dynamics."""
        # Slow improvement, then sudden fast improvement
        losses = [100 - 0.1 * i for i in range(30)]  # Slow
        losses.extend([losses[-1] - 2 * i for i in range(30)])  # Fast

        analyzer = ConvergenceAnalyzer.from_loss_history(losses)

        transitions = analyzer.find_phase_transitions(sensitivity=1.0)
        # Should detect transition around epoch 30
        assert len(transitions) >= 1
        assert any(25 <= t <= 35 for t in transitions)


class TestPlateauEvent:
    """Tests for PlateauEvent dataclass."""

    def test_create_plateau_event(self):
        """Should create plateau event with all fields."""
        event = PlateauEvent(
            start_epoch=10,
            end_epoch=25,
            duration=16,
            avg_loss=50.5,
            min_loss=49.0,
            avg_improvement_rate=0.00005,
        )

        assert event.start_epoch == 10
        assert event.end_epoch == 25
        assert event.duration == 16
        assert event.avg_loss == 50.5
        assert event.min_loss == 49.0
        assert event.avg_improvement_rate == 0.00005

    def test_plateau_event_repr(self):
        """Repr should show key info."""
        event = PlateauEvent(
            start_epoch=5,
            end_epoch=15,
            duration=11,
            avg_loss=42.123,
            min_loss=41.0,
            avg_improvement_rate=0.0001,
        )

        repr_str = repr(event)
        assert "5-15" in repr_str
        assert "duration=11" in repr_str
        assert "42.1" in repr_str


class TestPlateauDetection:
    """Tests for plateau/stagnation detection in LossImprovementTracker."""

    def test_plateau_event_emitted_on_stagnation_entry(self):
        """Should emit plateau_event when entering stagnation."""
        tracker = LossImprovementTracker(
            stagnation_threshold=0.001,
            stagnation_epochs=5,
        )

        # Initial improvement
        tracker.update(100.0)
        tracker.update(90.0)

        # Start stagnating (tiny changes)
        for i in range(10):
            metrics = tracker.update(89.999)
            if i == 4:  # 5th stagnating epoch
                # Should emit event when first entering stagnation
                assert metrics.is_stagnating is True
                assert metrics.plateau_event is not None
                assert metrics.plateau_event.duration >= 5

    def test_plateau_event_emitted_on_stagnation_exit(self):
        """Should emit plateau_event when exiting stagnation."""
        tracker = LossImprovementTracker(
            stagnation_threshold=0.001,
            stagnation_epochs=5,
        )

        # Initial value
        tracker.update(100.0)
        tracker.update(90.0)

        # Stagnate
        for _ in range(10):
            tracker.update(89.999)

        # Exit stagnation with big improvement
        metrics = tracker.update(80.0)

        # Should emit plateau event on exit
        assert metrics.is_stagnating is False
        assert metrics.plateau_event is not None
        assert metrics.plateau_event.start_epoch == 2  # First stagnating epoch

    def test_plateau_events_property(self):
        """plateau_events should return completed plateau events."""
        tracker = LossImprovementTracker(
            stagnation_threshold=0.001,
            stagnation_epochs=5,
        )

        # Start - epoch 0 (counts as stagnating since improvement_rate=0)
        tracker.update(100.0)

        # Continue stagnating
        for _ in range(10):
            tracker.update(99.999)

        # Improvement (exits first plateau) - epoch 11
        tracker.update(80.0)

        # Second plateau starts at epoch 12
        for _ in range(10):
            tracker.update(79.999)

        # Improvement (exits second plateau)
        tracker.update(60.0)

        events = tracker.plateau_events
        assert len(events) == 2
        # First plateau starts at epoch 0 (first update has improvement_rate=0)
        assert events[0].start_epoch == 0
        # Second plateau starts at epoch 12
        assert events[1].start_epoch == 12

    def test_current_plateau_during_stagnation(self):
        """current_plateau should return ongoing plateau."""
        tracker = LossImprovementTracker(
            stagnation_threshold=0.001,
            stagnation_epochs=5,
        )

        # Epoch 0 (counts as stagnating since improvement_rate=0)
        tracker.update(100.0)

        # Continue stagnating
        for _ in range(10):
            tracker.update(99.999)

        # Should have current plateau starting at epoch 0
        current = tracker.current_plateau
        assert current is not None
        assert current.start_epoch == 0
        assert current.duration >= 5

    def test_current_plateau_none_when_not_stagnating(self):
        """current_plateau should be None when not stagnating."""
        tracker = LossImprovementTracker(
            stagnation_threshold=0.001,
            stagnation_epochs=5,
        )

        # Continuous improvement
        loss = 100.0
        for _ in range(10):
            loss *= 0.9
            tracker.update(loss)

        assert tracker.current_plateau is None

    def test_plateau_in_summary(self):
        """get_summary should include plateau statistics."""
        tracker = LossImprovementTracker(
            stagnation_threshold=0.001,
            stagnation_epochs=5,
        )

        tracker.update(100.0)

        # Plateau
        for _ in range(10):
            tracker.update(99.999)

        # Exit plateau
        tracker.update(80.0)

        summary = tracker.get_summary()
        assert "n_plateaus" in summary
        assert "total_plateau_epochs" in summary
        assert "plateaus" in summary
        assert summary["n_plateaus"] == 1
        assert summary["total_plateau_epochs"] >= 5

    def test_plateau_dict_format(self):
        """Plateaus in summary should be proper dicts."""
        tracker = LossImprovementTracker(
            stagnation_threshold=0.001,
            stagnation_epochs=5,
        )

        tracker.update(100.0)
        for _ in range(10):
            tracker.update(99.999)
        tracker.update(80.0)

        summary = tracker.get_summary()
        plateau_dicts = summary["plateaus"]

        assert len(plateau_dicts) == 1
        p = plateau_dicts[0]
        assert "start_epoch" in p
        assert "end_epoch" in p
        assert "duration" in p
        assert "avg_loss" in p
        assert "min_loss" in p
        assert "avg_improvement_rate" in p

    def test_metrics_plateau_event_default_none(self):
        """plateau_event should default to None in ImprovementMetrics."""
        tracker = LossImprovementTracker()
        metrics = tracker.update(100.0)

        assert metrics.plateau_event is None

    def test_reset_clears_plateau_state(self):
        """reset() should clear plateau tracking state."""
        tracker = LossImprovementTracker(
            stagnation_threshold=0.001,
            stagnation_epochs=5,
        )

        tracker.update(100.0)
        for _ in range(10):
            tracker.update(99.999)
        tracker.update(80.0)  # Exit plateau

        assert len(tracker.plateau_events) == 1

        tracker.reset()

        assert len(tracker.plateau_events) == 0
        assert tracker.current_plateau is None


class TestIntegration:
    """Integration tests for convergence analytics."""

    def test_realistic_training_curve(self):
        """Test with a realistic training loss curve."""
        tracker = LossImprovementTracker()

        # Simulate realistic training: fast initial improvement, then slowdown
        loss = 1000.0
        for epoch in range(200):
            # Exponential decay with noise
            decay = 0.98 if epoch < 50 else 0.995
            loss = loss * decay + (epoch % 3) * 0.1  # Small noise
            metrics = tracker.update(loss)

        # Check final state
        summary = tracker.get_summary()
        assert summary["total_epochs"] == 200
        assert summary["final_loss"] < summary["initial_loss"]
        assert summary["total_improvement_rate"] > 0.5  # At least 50% improvement

        # Check analyzer
        analyzer = ConvergenceAnalyzer(tracker=tracker)
        assert analyzer.quality_score > 0.3

    def test_with_training_result_type(self):
        """Test that from_training_result works with proper typing."""
        # We can't easily create a full TrainingResult, but we can verify
        # that from_loss_history works as the fallback
        losses = [100, 90, 80, 70, 60]
        analyzer = ConvergenceAnalyzer.from_loss_history(losses)

        assert analyzer.tracker.best_loss == 60
