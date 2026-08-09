"""Tests for validation.dead_parameter_probe module."""
from temper_placer.validation.dead_parameter_probe import (
    ProbeRecord,
    measure_noise_floor,
    DEAD,
    LIVE,
)


class TestMeasureNoiseFloor:
    """Tests for measure_noise_floor."""

    def test_deterministic_function_zero_noise(self):
        """A deterministic function should return ~0.0 noise floor."""
        floor = measure_noise_floor(lambda: 42.0, samples=5)
        assert floor == 0.0

    def test_varying_function(self):
        """A function that alternates should have a non-zero floor."""
        values = iter([1.0, 3.0, 1.0, 3.0, 1.0])
        floor = measure_noise_floor(lambda: next(values), samples=5)
        assert floor == 2.0  # max=3.0, min=1.0, diff=2.0

    def test_single_sample(self):
        floor = measure_noise_floor(lambda: 7.0, samples=1)
        # max == min, so floor should be 0.0
        assert floor == 0.0

    def test_float_values(self):
        """Ensure float values are handled correctly."""
        values = iter([1.5, 2.5, 1.0])
        floor = measure_noise_floor(lambda: next(values), samples=3)
        assert floor == 1.5  # 2.5 - 1.0


class TestProbeRecord:
    """Tests for ProbeRecord."""

    def test_create_live_record(self):
        rec = ProbeRecord(
            target="gate:placement_complete.overlap_loss",
            kind="gate_input",
            disposition=LIVE,
            baseline_outcome="PASS",
            perturbed_outcome="FAIL",
            detail="verdict flipped",
        )
        assert rec.disposition == LIVE
        assert rec.target == "gate:placement_complete.overlap_loss"
        assert rec.delta is None
        assert rec.noise_floor is None

    def test_create_dead_record(self):
        rec = ProbeRecord(
            target="param:k_copper",
            kind="physics_parameter",
            disposition=DEAD,
            baseline_outcome=45.0,
            perturbed_outcome=45.0,
            delta=0.0,
            noise_floor=0.001,
            detail="no movement",
        )
        assert rec.disposition == DEAD
        assert rec.delta == 0.0
        assert rec.noise_floor == 0.001
