"""
Tests for validation_callback module.

Tests the ValidationCallback class and related functionality for
integrating DRC validation into the training loop.
"""

from pathlib import Path
from unittest.mock import MagicMock

import jax.numpy as jnp
import pytest

from temper_placer.optimizer.validation_callback import (
    ValidationCallback,
    ValidationConfig,
    ValidationResult,
    create_validation_callback,
)


class TestValidationConfig:
    """Tests for ValidationConfig dataclass."""

    def test_default_config(self):
        """Default config should have sensible values."""
        config = ValidationConfig()

        assert config.enabled is True
        assert config.drc_enabled is True
        assert config.drc_interval == 100
        assert config.drc_template_pcb is None
        assert config.drc_board_origin == (0.0, 0.0)
        assert config.fail_on_drc_errors is False
        assert config.spice_enabled is False

    def test_custom_config(self):
        """Custom config values should be stored correctly."""
        template = Path("/tmp/test.kicad_pcb")
        config = ValidationConfig(
            enabled=True,
            drc_enabled=True,
            drc_interval=50,
            drc_template_pcb=template,
            drc_board_origin=(100.0, 50.0),
            fail_on_drc_errors=True,
            max_drc_errors=5,
        )

        assert config.drc_interval == 50
        assert config.drc_template_pcb == template
        assert config.drc_board_origin == (100.0, 50.0)
        assert config.fail_on_drc_errors is True
        assert config.max_drc_errors == 5


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_default_result(self):
        """Default result should indicate pass."""
        result = ValidationResult(epoch=100)

        assert result.epoch == 100
        assert result.passed is True
        assert result.drc_penalty == 0.0
        assert result.drc_errors == 0
        assert result.messages == []

    def test_to_dict(self):
        """to_dict should serialize all fields."""
        result = ValidationResult(
            epoch=100,
            elapsed_ms=150.5,
            drc_penalty=5.2,
            drc_errors=2,
            drc_warnings=3,
            passed=False,
            messages=["Test message"],
        )

        d = result.to_dict()

        assert d["epoch"] == 100
        assert d["elapsed_ms"] == 150.5
        assert d["drc_penalty"] == 5.2
        assert d["drc_errors"] == 2
        assert d["drc_warnings"] == 3
        assert d["passed"] is False
        assert d["messages"] == ["Test message"]


class TestValidationCallback:
    """Tests for ValidationCallback class."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock LossContext."""
        context = MagicMock()
        comp1 = MagicMock()
        comp1.ref = "U1"
        comp2 = MagicMock()
        comp2.ref = "R1"
        context.netlist.components = [comp1, comp2]
        return context

    def test_disabled_callback_returns_none(self, mock_context):
        """Disabled callback should always return None."""
        config = ValidationConfig(enabled=False)
        callback = ValidationCallback(config=config)

        positions = jnp.array([[10.0, 20.0], [30.0, 40.0]])
        rotations = jnp.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])

        result = callback(0, positions, rotations, mock_context)
        assert result is None

    def test_should_validate_at_interval(self):
        """should_validate should respect drc_interval."""
        config = ValidationConfig(
            enabled=True,
            drc_enabled=True,
            drc_interval=50,
            drc_template_pcb=Path("/tmp/test.kicad_pcb"),
        )
        callback = ValidationCallback(config=config)

        # Should validate at epoch 0
        assert callback.should_validate(0) is True

        # Should NOT validate between intervals
        assert callback.should_validate(25) is False
        assert callback.should_validate(49) is False

        # Should validate at interval
        assert callback.should_validate(50) is True
        assert callback.should_validate(100) is True

    def test_should_validate_disabled(self):
        """should_validate returns False when disabled."""
        config = ValidationConfig(enabled=False)
        callback = ValidationCallback(config=config)

        assert callback.should_validate(0) is False
        assert callback.should_validate(100) is False

    def test_history_accumulates(self, mock_context):
        """Callback should accumulate results in history."""
        # Create callback with DRC disabled (so no external deps)
        config = ValidationConfig(
            enabled=True,
            drc_enabled=False,
            spice_enabled=False,
        )
        callback = ValidationCallback(config=config)

        # No validation should happen with both DRC and SPICE disabled
        assert callback.should_validate(0) is False
        assert len(callback.history) == 0

    def test_reset_clears_history(self):
        """reset should clear history."""
        config = ValidationConfig(enabled=True, drc_enabled=False)
        callback = ValidationCallback(config=config)

        # Manually add to history
        callback._history.append(ValidationResult(epoch=0))
        callback._history.append(ValidationResult(epoch=100))
        assert len(callback.history) == 2

        callback.reset()
        assert len(callback.history) == 0

    def test_on_result_callback_invoked(self, mock_context):
        """on_result callback should be invoked after validation."""
        results_received = []

        def on_result(result):
            results_received.append(result)

        # Create callback with mocked DRC loss
        config = ValidationConfig(
            enabled=True,
            drc_enabled=True,
            drc_interval=1,
        )

        mock_drc_loss = MagicMock()
        mock_drc_loss.is_available.return_value = True
        mock_entry = MagicMock()
        mock_entry.penalty = 10.0
        mock_entry.result = MagicMock()
        mock_entry.result.error_count = 2
        mock_entry.result.warning_count = 1
        mock_drc_loss.evaluate.return_value = mock_entry

        callback = ValidationCallback(
            config=config,
            drc_loss=mock_drc_loss,
            on_result=on_result,
        )
        callback._initialized = True

        positions = jnp.array([[10.0, 20.0], [30.0, 40.0]])
        rotations = jnp.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])

        result = callback(0, positions, rotations, mock_context)

        assert len(results_received) == 1
        assert results_received[0].drc_penalty == 10.0
        assert results_received[0].drc_errors == 2

    def test_fail_on_drc_errors(self, mock_context):
        """Should mark as failed when DRC errors exceed threshold."""
        config = ValidationConfig(
            enabled=True,
            drc_enabled=True,
            drc_interval=1,
            fail_on_drc_errors=True,
            max_drc_errors=1,
        )

        mock_drc_loss = MagicMock()
        mock_drc_loss.is_available.return_value = True
        mock_entry = MagicMock()
        mock_entry.penalty = 10.0
        mock_entry.result = MagicMock()
        mock_entry.result.error_count = 5  # Exceeds threshold of 1
        mock_entry.result.warning_count = 0
        mock_drc_loss.evaluate.return_value = mock_entry

        callback = ValidationCallback(config=config, drc_loss=mock_drc_loss)
        callback._initialized = True

        positions = jnp.array([[10.0, 20.0], [30.0, 40.0]])
        rotations = jnp.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])

        result = callback(0, positions, rotations, mock_context)

        assert result is not None
        assert result.passed is False
        assert "exceed threshold" in result.messages[0]

    def test_drc_exception_handled(self, mock_context):
        """DRC exceptions should be caught and logged."""
        config = ValidationConfig(
            enabled=True,
            drc_enabled=True,
            drc_interval=1,
            log_validation=False,  # Suppress logging in tests
        )

        mock_drc_loss = MagicMock()
        mock_drc_loss.is_available.return_value = True
        mock_drc_loss.evaluate.side_effect = Exception("DRC crashed")

        callback = ValidationCallback(config=config, drc_loss=mock_drc_loss)
        callback._initialized = True

        positions = jnp.array([[10.0, 20.0], [30.0, 40.0]])
        rotations = jnp.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])

        # Should not raise
        result = callback(0, positions, rotations, mock_context)

        assert result is not None
        assert "DRC validation failed" in result.messages[0]

    def test_summary_no_validations(self):
        """Summary should handle empty history."""
        config = ValidationConfig(enabled=True, drc_enabled=False)
        callback = ValidationCallback(config=config)

        summary = callback.summary()
        assert "No validations run yet" in summary

    def test_summary_with_history(self):
        """Summary should report on history."""
        config = ValidationConfig(enabled=True, drc_enabled=True)
        callback = ValidationCallback(config=config)

        # Add some results
        callback._history.append(ValidationResult(epoch=0, drc_penalty=20.0, drc_errors=5))
        callback._history.append(ValidationResult(epoch=50, drc_penalty=10.0, drc_errors=2))
        callback._history.append(ValidationResult(epoch=100, drc_penalty=5.0, drc_errors=0))

        summary = callback.summary()

        assert "3 runs" in summary
        assert "min=5.0" in summary.lower() or "min=5.00" in summary
        assert "All validations passed" in summary


class TestCreateValidationCallback:
    """Tests for create_validation_callback factory function."""

    def test_creates_callback_with_template(self, tmp_path):
        """Should create callback with DRC enabled when template provided."""
        template = tmp_path / "test.kicad_pcb"
        template.write_text("(kicad_pcb ...)")

        callback = create_validation_callback(
            template_pcb=template,
            board_origin=(100.0, 50.0),
            drc_interval=25,
        )

        assert callback.config.drc_enabled is True
        assert callback.config.drc_interval == 25
        assert callback.config.drc_template_pcb == template
        assert callback.config.drc_board_origin == (100.0, 50.0)

    def test_creates_callback_without_template(self):
        """Should create callback with DRC disabled when no template."""
        callback = create_validation_callback()

        assert callback.config.drc_enabled is False

    def test_on_result_passed_through(self):
        """on_result callback should be passed through."""
        results = []

        def on_result(result):
            results.append(result)

        callback = create_validation_callback(on_result=on_result)

        assert callback._on_result is on_result
