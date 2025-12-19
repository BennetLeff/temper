"""
Tests for DRC loss function with caching.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import jax.numpy as jnp
import pytest

from temper_placer.losses.drc_loss import (
    DRCCacheEntry,
    DRCHistory,
    DRCLoss,
    create_drc_loss,
)
from temper_placer.validation.base import ValidationSeverity
from temper_placer.validation.drc import (
    DRCResult,
    DRCViolation,
    DRCViolationType,
    KiCadDRCValidator,
)

# =============================================================================
# DRCCacheEntry Tests
# =============================================================================


class TestDRCCacheEntry:
    """Tests for DRCCacheEntry dataclass."""

    def test_basic_creation(self):
        """Test creating a cache entry."""
        entry = DRCCacheEntry(penalty=5.0, epoch=10)
        assert entry.penalty == 5.0
        assert entry.epoch == 10
        assert entry.result is None
        assert entry.elapsed_ms == 0.0

    def test_with_result(self):
        """Test cache entry with full DRC result."""
        result = DRCResult(success=True, error_count=2, warning_count=5)
        entry = DRCCacheEntry(
            penalty=15.0,
            epoch=50,
            result=result,
            elapsed_ms=250.0,
        )
        assert entry.penalty == 15.0
        assert entry.result is not None
        assert entry.result.error_count == 2
        assert entry.elapsed_ms == 250.0


# =============================================================================
# DRCHistory Tests
# =============================================================================


class TestDRCHistory:
    """Tests for DRCHistory tracking."""

    def test_empty_history(self):
        """Test empty history defaults."""
        history = DRCHistory()
        assert history.total_evaluations == 0
        assert history.total_time_ms == 0.0
        assert history.best_penalty() == float("inf")
        assert history.latest_penalty() == float("inf")
        assert history.improvement_trend() == 0.0

    def test_add_entry(self):
        """Test adding entries to history."""
        history = DRCHistory()
        history.add(epoch=0, penalty=10.0, errors=5, warnings=3, elapsed_ms=100)

        assert history.total_evaluations == 1
        assert history.total_time_ms == 100.0
        assert len(history.entries) == 1
        assert history.entries[0] == (0, 10.0)
        assert history.violation_counts[0] == (0, 5, 3)

    def test_best_penalty(self):
        """Test best penalty tracking."""
        history = DRCHistory()
        history.add(0, 20.0)
        history.add(10, 15.0)
        history.add(20, 25.0)  # Worse
        history.add(30, 5.0)  # Best
        history.add(40, 10.0)

        assert history.best_penalty() == 5.0

    def test_latest_penalty(self):
        """Test latest penalty tracking."""
        history = DRCHistory()
        history.add(0, 20.0)
        history.add(10, 15.0)
        history.add(20, 8.0)

        assert history.latest_penalty() == 8.0

    def test_improvement_trend_improving(self):
        """Test trend calculation when improving."""
        history = DRCHistory()
        # Consistently improving: 50 -> 40 -> 30 -> 20 -> 10
        for i, p in enumerate([50.0, 40.0, 30.0, 20.0, 10.0]):
            history.add(i * 10, p)

        trend = history.improvement_trend()
        assert trend > 0, "Trend should be positive when improving"

    def test_improvement_trend_worsening(self):
        """Test trend calculation when worsening."""
        history = DRCHistory()
        # Consistently worsening: 10 -> 20 -> 30 -> 40 -> 50
        for i, p in enumerate([10.0, 20.0, 30.0, 40.0, 50.0]):
            history.add(i * 10, p)

        trend = history.improvement_trend()
        assert trend < 0, "Trend should be negative when worsening"

    def test_improvement_trend_stable(self):
        """Test trend calculation when stable."""
        history = DRCHistory()
        # Stable at 10.0
        for i in range(5):
            history.add(i * 10, 10.0)

        trend = history.improvement_trend()
        assert abs(trend) < 0.01, "Trend should be near zero when stable"

    def test_improvement_trend_window(self):
        """Test trend uses window parameter."""
        history = DRCHistory()
        # Old entries: worse
        for i in range(10):
            history.add(i * 10, 50.0)
        # Recent entries: much better
        for i in range(5):
            history.add((10 + i) * 10, 10.0 - i * 2)

        # With window=5, should only see recent improving trend
        trend = history.improvement_trend(window=5)
        assert trend > 0

    def test_summary(self):
        """Test summary string generation."""
        history = DRCHistory()
        history.add(0, 20.0, errors=5, warnings=10, elapsed_ms=100)
        history.add(50, 10.0, errors=2, warnings=5, elapsed_ms=150)

        summary = history.summary()
        assert "2 evaluations" in summary
        assert "250ms" in summary
        assert "Best penalty: 10.00" in summary
        assert "Latest penalty: 10.00" in summary
        assert "2 errors" in summary
        assert "5 warnings" in summary


# =============================================================================
# DRCLoss Tests
# =============================================================================


class TestDRCLoss:
    """Tests for DRCLoss class."""

    @pytest.fixture
    def mock_validator(self):
        """Create a mock validator."""
        validator = MagicMock(spec=KiCadDRCValidator)
        validator.is_available.return_value = True
        validator.compute_penalty.return_value = 5.0
        return validator

    @pytest.fixture
    def mock_exporter(self):
        """Create a mock PCB exporter."""

        def exporter(positions, rotations, context):
            # Create a temp file
            tmp = tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False)
            tmp.close()
            return Path(tmp.name)

        return exporter

    @pytest.fixture
    def sample_context(self):
        """Create a sample loss context."""
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Component, Netlist, Pin
        from temper_placer.losses.base import LossContext

        components = [
            Component(
                ref="R1",
                footprint="0805",
                bounds=(2.0, 1.25),
                pins=[Pin("1", "1", (0, 0)), Pin("2", "2", (1.5, 0))],
            ),
            Component(
                ref="R2",
                footprint="0805",
                bounds=(2.0, 1.25),
                pins=[Pin("1", "1", (0, 0)), Pin("2", "2", (1.5, 0))],
            ),
        ]
        netlist = Netlist(components=components, nets=[])
        board = Board(width=100, height=100)

        return LossContext.from_netlist_and_board(netlist, board)

    def test_name(self):
        """Test loss function name."""
        loss = DRCLoss()
        assert loss.name == "drc_loss"

    def test_default_not_available(self):
        """Test that DRC is not available without exporter."""
        loss = DRCLoss()
        assert not loss.is_available()

    def test_available_with_mocks(self, mock_validator, mock_exporter):
        """Test availability with mocked dependencies."""
        loss = DRCLoss(validator=mock_validator, pcb_exporter=mock_exporter)
        assert loss.is_available()

    def test_eval_interval(self):
        """Test eval interval getter/setter."""
        loss = DRCLoss(eval_interval=100)
        assert loss.eval_interval == 100

        loss.eval_interval = 50
        assert loss.eval_interval == 50

        # Minimum of 1
        loss.eval_interval = 0
        assert loss.eval_interval == 1

    def test_should_evaluate_first_epoch(self, mock_validator, mock_exporter):
        """Test that first epoch always evaluates."""
        loss = DRCLoss(validator=mock_validator, pcb_exporter=mock_exporter, eval_interval=10)
        assert loss.should_evaluate(0)

    def test_should_evaluate_interval(self, mock_validator, mock_exporter):
        """Test interval-based evaluation."""
        loss = DRCLoss(validator=mock_validator, pcb_exporter=mock_exporter, eval_interval=10)

        # Manually set last eval and cache (both needed for interval check)
        loss._last_eval_epoch = 0
        loss._cache = DRCCacheEntry(penalty=5.0, epoch=0)  # Set a cache entry

        assert not loss.should_evaluate(5)  # Too soon
        assert loss.should_evaluate(10)  # Exactly at interval
        assert loss.should_evaluate(15)  # Past interval

    def test_cached_penalty_default(self):
        """Test default cached penalty."""
        loss = DRCLoss(base_penalty=0.0)
        assert loss.cached_penalty == 0.0

    def test_set_cached_penalty(self):
        """Test manually setting cached penalty."""
        loss = DRCLoss()
        loss.set_cached_penalty(15.0, epoch=50)

        assert loss.cached_penalty == 15.0
        assert loss._last_eval_epoch == 50

    def test_reset_cache(self, mock_validator, mock_exporter):
        """Test cache reset."""
        loss = DRCLoss(validator=mock_validator, pcb_exporter=mock_exporter)
        loss.set_cached_penalty(10.0, epoch=100)
        loss._history.add(100, 10.0)

        loss.reset_cache()

        assert loss._cache is None
        assert loss._last_eval_epoch == -1
        assert loss.history.total_evaluations == 0

    def test_call_returns_cached(self, sample_context):
        """Test that __call__ returns cached penalty."""
        loss = DRCLoss(base_penalty=7.5)
        loss.set_cached_penalty(12.0, epoch=10)

        positions = jnp.zeros((2, 2))
        rotations = jnp.zeros((2, 4))

        result = loss(positions, rotations, sample_context)

        assert float(result.value) == 12.0
        assert "drc_penalty" in result.breakdown
        assert float(result.breakdown["drc_penalty"]) == 12.0

    def test_evaluate_updates_cache(self, mock_validator, mock_exporter, sample_context):
        """Test that evaluate() updates the cache."""
        drc_result = DRCResult(success=True, error_count=2, warning_count=5)
        mock_validator.run_drc.return_value = drc_result
        mock_validator.compute_penalty.return_value = 20.0

        loss = DRCLoss(
            validator=mock_validator,
            pcb_exporter=mock_exporter,
            cache_results=True,
        )

        positions = jnp.zeros((2, 2))
        rotations = jnp.zeros((2, 4))

        entry = loss.evaluate(positions, rotations, sample_context, epoch=10)

        assert entry.penalty == 20.0
        assert entry.epoch == 10
        assert loss.history.total_evaluations == 1

    def test_evaluate_failed_drc(self, mock_validator, mock_exporter, sample_context):
        """Test handling of failed DRC."""
        drc_result = DRCResult(success=False, raw_output="Error message")
        mock_validator.run_drc.return_value = drc_result

        loss = DRCLoss(
            validator=mock_validator,
            pcb_exporter=mock_exporter,
            fail_penalty=100.0,
        )

        positions = jnp.zeros((2, 2))
        rotations = jnp.zeros((2, 4))

        entry = loss.evaluate(positions, rotations, sample_context, epoch=10)

        assert entry.penalty == 100.0

    def test_compute_with_epoch_caching(self, mock_validator, mock_exporter, sample_context):
        """Test compute_with_epoch respects interval."""
        drc_result = DRCResult(success=True, error_count=0, warning_count=0)
        mock_validator.run_drc.return_value = drc_result
        mock_validator.compute_penalty.return_value = 5.0

        loss = DRCLoss(
            validator=mock_validator,
            pcb_exporter=mock_exporter,
            eval_interval=10,
        )

        positions = jnp.zeros((2, 2))
        rotations = jnp.zeros((2, 4))

        # First call should evaluate
        result1 = loss.compute_with_epoch(positions, rotations, sample_context, epoch=0)
        assert mock_validator.run_drc.call_count == 1

        # Within interval - should use cache
        result2 = loss.compute_with_epoch(positions, rotations, sample_context, epoch=5)
        assert mock_validator.run_drc.call_count == 1  # No new call

        # At interval - should evaluate again
        result3 = loss.compute_with_epoch(positions, rotations, sample_context, epoch=10)
        assert mock_validator.run_drc.call_count == 2

    def test_get_violations_empty(self):
        """Test get_violations with no result."""
        loss = DRCLoss()
        assert loss.get_violations() == []

    def test_get_violations_with_result(self, mock_validator, mock_exporter, sample_context):
        """Test get_violations returns violations."""
        violations = [
            DRCViolation(
                severity=ValidationSeverity.ERROR,
                code="DRC_CLEARANCE",
                message="Clearance violation",
                violation_type=DRCViolationType.CLEARANCE,
            ),
        ]
        drc_result = DRCResult(success=True, violations=violations, error_count=1)
        mock_validator.run_drc.return_value = drc_result
        mock_validator.compute_penalty.return_value = 10.0

        loss = DRCLoss(
            validator=mock_validator,
            pcb_exporter=mock_exporter,
            cache_results=True,
        )

        positions = jnp.zeros((2, 2))
        rotations = jnp.zeros((2, 4))

        loss.evaluate(positions, rotations, sample_context, epoch=0)

        violations = loss.get_violations()
        assert len(violations) == 1
        assert violations[0].violation_type == DRCViolationType.CLEARANCE

    def test_to_dict(self, mock_validator, mock_exporter):
        """Test to_dict serialization."""
        loss = DRCLoss(
            validator=mock_validator,
            pcb_exporter=mock_exporter,
            eval_interval=25,
        )
        loss.set_cached_penalty(8.0, epoch=50)
        loss._history.add(50, 8.0)

        d = loss.to_dict()

        assert d["name"] == "drc_loss"
        assert d["eval_interval"] == 25
        assert d["is_available"] == True
        assert d["cached_penalty"] == 8.0
        assert d["last_eval_epoch"] == 50
        assert d["history"]["total_evaluations"] == 1
        assert d["history"]["best_penalty"] == 8.0

    def test_history_property(self):
        """Test history property access."""
        loss = DRCLoss()
        assert isinstance(loss.history, DRCHistory)
        assert loss.history.total_evaluations == 0


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestCreateDRCLoss:
    """Tests for create_drc_loss factory function."""

    def test_default_creation(self):
        """Test creating DRC loss with defaults."""
        loss = create_drc_loss()

        assert loss.name == "drc_loss"
        assert loss.eval_interval == 50
        assert not loss.is_available()  # No exporter

    def test_custom_interval(self):
        """Test custom evaluation interval."""
        loss = create_drc_loss(eval_interval=100)
        assert loss.eval_interval == 100

    def test_custom_weights(self):
        """Test custom penalty weights."""
        severity_weights = {"error": 20.0, "warning": 2.0}
        violation_weights = {"clearance": 5.0}

        loss = create_drc_loss(
            severity_weights=severity_weights,
            violation_weights=violation_weights,
        )

        # Verify weights are passed to validator
        assert loss.validator.severity_weights["error"] == 20.0
        assert loss.validator.violation_weights["clearance"] == 5.0


# =============================================================================
# Integration Tests
# =============================================================================


class TestDRCLossIntegration:
    """Integration tests for DRC loss."""

    def test_training_loop_simulation(self):
        """Simulate DRC loss in a training loop."""
        # Create loss without actual DRC (returns base penalty)
        loss = DRCLoss(base_penalty=50.0, eval_interval=10)

        penalties = []
        for epoch in range(50):
            # Simulate manual penalty updates
            if epoch % 10 == 0:
                # Simulate improvement
                new_penalty = max(0, 50.0 - epoch)
                loss.set_cached_penalty(new_penalty, epoch)
                loss.history.add(epoch, new_penalty)

            penalties.append(loss.cached_penalty)

        # Should see decreasing penalties
        assert penalties[0] >= penalties[-1]
        assert loss.history.total_evaluations == 5  # 0, 10, 20, 30, 40

    def test_loss_result_format(self):
        """Test loss result has correct format for composite loss."""
        loss = DRCLoss(base_penalty=10.0)
        loss.set_cached_penalty(15.0, epoch=5)

        positions = jnp.zeros((5, 2))
        rotations = jnp.zeros((5, 4))

        # Create minimal context
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.losses.base import LossContext

        components = [
            Component(ref=f"R{i}", footprint="0805", bounds=(2.0, 1.25), pins=[]) for i in range(5)
        ]
        netlist = Netlist(components=components, nets=[])
        board = Board(width=100, height=100)
        context = LossContext.from_netlist_and_board(netlist, board)

        result = loss(positions, rotations, context)

        # Verify LossResult format
        assert hasattr(result, "value")
        assert hasattr(result, "breakdown")
        assert float(result.value) == 15.0
        assert isinstance(result.breakdown, dict)
