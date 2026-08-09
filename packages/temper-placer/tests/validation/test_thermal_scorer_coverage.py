"""Tests for validation.thermal_scorer — falsifiability_assertion."""
import numpy as np

from temper_placer.validation.thermal_scorer import falsifiability_assertion


class TestFalsifiabilityAssertion:
    """Tests for the falsifiability assertion function."""

    def test_identical_fields_return_false(self):
        """Identical fields should never be flagged as divergent."""
        u5 = np.ones((10, 10), dtype=np.float64) * 30.0
        u7 = np.ones((10, 10), dtype=np.float64) * 30.0
        assert falsifiability_assertion(u5, u7) is False

    def test_small_difference_below_threshold(self):
        """A difference below the falsifiability threshold should return False."""
        u5 = np.zeros((5, 5), dtype=np.float64)
        u7 = np.ones((5, 5), dtype=np.float64) * 0.5  # max diff = 0.5 < 1.0
        assert falsifiability_assertion(u5, u7) is False

    def test_large_difference_above_threshold(self):
        """A difference above the falsifiability threshold should return True."""
        u5 = np.zeros((5, 5), dtype=np.float64)
        u7 = np.ones((5, 5), dtype=np.float64) * 5.0  # max diff = 5.0 > 1.0
        assert falsifiability_assertion(u5, u7) is True

    def test_exact_threshold(self):
        """Test behavior at exactly the threshold."""
        u5 = np.zeros((5, 5), dtype=np.float64)
        u7 = np.ones((5, 5), dtype=np.float64) * 1.0  # max diff = 1.0 == threshold
        assert falsifiability_assertion(u5, u7) is False  # > not >=

    def test_just_above_threshold(self):
        u5 = np.zeros((5, 5), dtype=np.float64)
        u7 = np.ones((5, 5), dtype=np.float64) * 1.0001
        assert falsifiability_assertion(u5, u7) is True

    def test_different_shapes_work(self):
        """Should work with any compatible shapes for np.abs."""
        u5 = np.array([0.0, 0.0, 0.0])
        u7 = np.array([2.0, 1.0, 0.5])
        assert falsifiability_assertion(u5, u7) is True

    def test_single_element(self):
        u5 = np.array([0.0])
        u7 = np.array([1.5])
        assert falsifiability_assertion(u5, u7) is True
