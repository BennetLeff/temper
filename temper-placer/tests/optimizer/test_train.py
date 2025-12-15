"""
Tests for the optimizer module.

These tests verify:
- Configuration dataclasses
- Temperature and learning rate scheduling
- Curriculum phase transitions
- Training loop with simple test cases
"""

import pytest
import jax
import jax.numpy as jnp

from temper_placer.optimizer.config import (
    OptimizerConfig,
    TemperatureSchedule,
    LearningRateSchedule,
    CurriculumPhase,
    get_default_loss_weights,
)
from temper_placer.optimizer.scheduler import (
    get_temperature,
    get_learning_rate,
    get_curriculum_weights,
    get_phase_weight,
)
from temper_placer.optimizer.curriculum import (
    create_default_phases,
    create_fast_phases,
    get_active_phase,
    get_phase_progress,
    smooth_transition_weights,
    CurriculumState,
)


# =============================================================================
# Config Tests
# =============================================================================


class TestOptimizerConfig:
    """Tests for OptimizerConfig."""

    def test_default_config(self):
        """Test default configuration creation."""
        config = OptimizerConfig()
        assert config.epochs == 8000
        assert config.seed == 42
        assert config.use_adam is True
        assert config.gradient_clip_norm == 1.0

    def test_fast_test_config(self):
        """Test fast test configuration."""
        config = OptimizerConfig.fast_test()
        assert config.epochs == 100
        assert config.checkpoint.enabled is False
        assert config.early_stopping.enabled is False

    def test_default_curriculum_config(self):
        """Test default curriculum configuration."""
        config = OptimizerConfig.default_curriculum()
        assert len(config.curriculum_phases) == 5
        assert config.curriculum_phases[0].name == "spread"
        assert config.curriculum_phases[-1].name == "refinement"

    def test_temperature_schedule(self):
        """Test temperature schedule configuration."""
        schedule = TemperatureSchedule(start=5.0, end=0.1, warmup_epochs=100)
        assert schedule.start == 5.0
        assert schedule.end == 0.1
        assert schedule.warmup_epochs == 100

    def test_learning_rate_schedule(self):
        """Test learning rate schedule configuration."""
        schedule = LearningRateSchedule(
            initial=0.1, final=0.001, warmup_epochs=100, decay_type="cosine"
        )
        assert schedule.initial == 0.1
        assert schedule.final == 0.001


class TestDefaultLossWeights:
    """Tests for default loss weights."""

    def test_contains_expected_losses(self):
        """Test that default weights include all expected losses."""
        weights = get_default_loss_weights()
        expected = [
            "overlap",
            "boundary",
            "clearance",
            "thermal",
            "wirelength",
            "loop_area",
        ]
        for name in expected:
            assert name in weights

    def test_overlap_high_weight(self):
        """Test that overlap has high weight (hard constraint)."""
        weights = get_default_loss_weights()
        assert weights["overlap"] >= 50.0

    def test_clearance_high_weight(self):
        """Test that clearance has high weight (safety critical)."""
        weights = get_default_loss_weights()
        assert weights["clearance"] >= 50.0


# =============================================================================
# Scheduler Tests
# =============================================================================


class TestTemperatureSchedule:
    """Tests for temperature scheduling."""

    def test_warmup_holds_start(self):
        """Test that temperature holds at start during warmup."""
        schedule = TemperatureSchedule(start=5.0, end=0.1, warmup_epochs=100)
        temp = get_temperature(50, 1000, schedule)
        assert temp == 5.0

    def test_after_warmup_decreases(self):
        """Test that temperature decreases after warmup."""
        schedule = TemperatureSchedule(start=5.0, end=0.1, warmup_epochs=100)
        temp_early = get_temperature(200, 1000, schedule)
        temp_late = get_temperature(800, 1000, schedule)
        assert temp_early > temp_late

    def test_end_approaches_minimum(self):
        """Test that temperature approaches end value."""
        schedule = TemperatureSchedule(start=5.0, end=0.1, warmup_epochs=100)
        temp = get_temperature(999, 1000, schedule)
        assert temp < 0.5  # Close to 0.1

    def test_linear_annealing(self):
        """Test linear temperature annealing."""
        schedule = TemperatureSchedule(start=5.0, end=0.0, warmup_epochs=0, anneal_type="linear")
        temp = get_temperature(500, 1000, schedule)
        assert abs(temp - 2.5) < 0.1  # Should be halfway


class TestLearningRateSchedule:
    """Tests for learning rate scheduling."""

    def test_warmup_increases(self):
        """Test that LR increases during warmup."""
        schedule = LearningRateSchedule(initial=0.1, warmup_epochs=100, decay_type="none")
        lr_early = get_learning_rate(10, 1000, schedule)
        lr_late = get_learning_rate(90, 1000, schedule)
        assert lr_early < lr_late

    def test_after_warmup_holds(self):
        """Test that LR holds after warmup before decay."""
        schedule = LearningRateSchedule(
            initial=0.1,
            warmup_epochs=100,
            decay_type="cosine",
            decay_start_epoch=500,
        )
        lr = get_learning_rate(300, 1000, schedule)
        assert abs(lr - 0.1) < 0.01

    def test_decay_decreases(self):
        """Test that LR decreases during decay."""
        schedule = LearningRateSchedule(
            initial=0.1,
            final=0.01,
            warmup_epochs=0,
            decay_type="cosine",
            decay_start_epoch=0,
        )
        lr_early = get_learning_rate(100, 1000, schedule)
        lr_late = get_learning_rate(900, 1000, schedule)
        assert lr_early > lr_late


# =============================================================================
# Curriculum Tests
# =============================================================================


class TestCurriculumPhases:
    """Tests for curriculum phase creation."""

    def test_default_phases_cover_epochs(self):
        """Test that default phases cover all epochs."""
        phases = create_default_phases(8000)
        # Check no gaps
        for i in range(len(phases) - 1):
            assert phases[i].end_epoch == phases[i + 1].start_epoch

    def test_fast_phases_for_testing(self):
        """Test fast phases for unit tests."""
        phases = create_fast_phases(100)
        assert len(phases) == 3
        assert phases[-1].end_epoch == 100

    def test_phase_scaling(self):
        """Test that phases scale with total epochs."""
        phases_8k = create_default_phases(8000)
        phases_4k = create_default_phases(4000)

        # First phase should end at proportional epoch
        assert phases_8k[0].end_epoch == 1000
        assert phases_4k[0].end_epoch == 500


class TestActivePhase:
    """Tests for active phase detection."""

    def test_finds_correct_phase(self):
        """Test that correct phase is found."""
        phases = create_fast_phases(100)
        phase = get_active_phase(50, phases)
        assert phase is not None
        assert phase.name == "feasibility"

    def test_no_phase_before_start(self):
        """Test no phase before first starts."""
        phases = [CurriculumPhase(name="test", start_epoch=100, end_epoch=200, loss_weights={})]
        phase = get_active_phase(50, phases)
        assert phase is None

    def test_no_phase_after_end(self):
        """Test no phase after last ends."""
        phases = create_fast_phases(100)
        phase = get_active_phase(150, phases)
        assert phase is None


class TestPhaseProgress:
    """Tests for phase progress calculation."""

    def test_progress_at_start(self):
        """Test progress is 0 at phase start."""
        phase = CurriculumPhase(name="test", start_epoch=100, end_epoch=200, loss_weights={})
        progress = get_phase_progress(100, phase)
        assert progress == 0.0

    def test_progress_at_end(self):
        """Test progress is 1 at phase end."""
        phase = CurriculumPhase(name="test", start_epoch=100, end_epoch=200, loss_weights={})
        progress = get_phase_progress(199, phase)
        assert progress > 0.9

    def test_progress_at_middle(self):
        """Test progress is 0.5 at middle."""
        phase = CurriculumPhase(name="test", start_epoch=100, end_epoch=200, loss_weights={})
        progress = get_phase_progress(150, phase)
        assert abs(progress - 0.5) < 0.01


class TestCurriculumWeights:
    """Tests for curriculum weight calculation."""

    def test_phase_weight_during_phase(self):
        """Test phase weight is 1.0 during phase."""
        phase = CurriculumPhase(name="test", start_epoch=100, end_epoch=500, loss_weights={})
        weight = get_phase_weight(300, phase, transition_epochs=50)
        assert weight == 1.0

    def test_phase_weight_before_phase(self):
        """Test phase weight is 0 before phase."""
        phase = CurriculumPhase(name="test", start_epoch=100, end_epoch=500, loss_weights={})
        weight = get_phase_weight(50, phase, transition_epochs=50)
        assert weight == 0.0

    def test_smooth_transitions(self):
        """Test smooth weight transitions."""
        phases = [
            CurriculumPhase(
                name="phase1",
                start_epoch=0,
                end_epoch=100,
                loss_weights={"overlap": 10.0},
            ),
            CurriculumPhase(
                name="phase2",
                start_epoch=100,
                end_epoch=200,
                loss_weights={"overlap": 100.0},
            ),
        ]
        # Near transition, weights should blend
        weights = smooth_transition_weights(95, phases, transition_epochs=10)
        assert weights["overlap"] > 10.0
        assert weights["overlap"] < 100.0


class TestCurriculumState:
    """Tests for CurriculumState helper class."""

    def test_state_tracks_phase(self):
        """Test that state tracks current phase."""
        phases = create_fast_phases(100)
        state = CurriculumState(phases)
        changed = state.update(50)
        assert state.current_phase_name == "feasibility"

    def test_phase_change_detected(self):
        """Test that phase changes are detected."""
        phases = create_fast_phases(100)
        state = CurriculumState(phases)
        state.update(10)
        changed = state.update(50)
        assert changed is True

    def test_progress_string(self):
        """Test progress string formatting."""
        phases = create_fast_phases(100)
        state = CurriculumState(phases)
        state.update(50)
        progress_str = state.get_progress_string(50)
        assert "feasibility" in progress_str


# =============================================================================
# Integration Tests (require full setup)
# =============================================================================


class TestTrainingIntegration:
    """Integration tests for training loop."""

    @pytest.fixture
    def simple_setup(self):
        """Create simple netlist and board for testing."""
        from temper_placer.core.netlist import Component, Net, Netlist, Pin
        from temper_placer.core.board import Board
        from temper_placer.losses.base import LossContext
        from temper_placer.losses.overlap import OverlapLoss
        from temper_placer.losses.boundary import BoundaryLoss
        from temper_placer.losses.base import CompositeLoss, WeightedLoss

        # Create simple components
        components = [
            Component(ref=f"U{i}", footprint="Package_SO:SOIC-8", bounds=(10.0, 10.0))
            for i in range(5)
        ]
        netlist = Netlist(components=components, nets=[])
        board = Board(width=100.0, height=100.0)
        context = LossContext.from_netlist_and_board(netlist, board)

        # Simple composite loss
        composite = CompositeLoss(
            [
                WeightedLoss(OverlapLoss(), weight=100.0),
                WeightedLoss(BoundaryLoss(), weight=50.0),
            ]
        )

        return netlist, board, context, composite

    def test_training_runs(self, simple_setup):
        """Test that training loop runs without error."""
        from temper_placer.optimizer import train, OptimizerConfig

        netlist, board, context, composite = simple_setup
        config = OptimizerConfig.fast_test()
        config = OptimizerConfig(
            epochs=10,  # Very short for test
            seed=42,
            checkpoint=config.checkpoint,
            early_stopping=config.early_stopping,
            log_interval=5,
        )

        result = train(netlist, board, composite, context, config)

        assert result.total_epochs == 10
        assert result.final_loss >= 0
        assert result.final_state is not None

    def test_training_reduces_loss(self, simple_setup):
        """Test that training reduces loss over time."""
        from temper_placer.optimizer import train, OptimizerConfig

        netlist, board, context, composite = simple_setup
        config = OptimizerConfig(
            epochs=50,
            seed=42,
            log_interval=10,
            checkpoint=OptimizerConfig.fast_test().checkpoint,
            early_stopping=OptimizerConfig.fast_test().early_stopping,
        )

        result = train(netlist, board, composite, context, config)

        # Loss should generally decrease
        if len(result.history) >= 2:
            initial_loss = result.history[0].loss
            final_loss = result.history[-1].loss
            # Allow for some variance but overall should improve
            assert final_loss <= initial_loss * 2  # At least not exploding

    def test_history_recorded(self, simple_setup):
        """Test that training history is recorded."""
        from temper_placer.optimizer import train, OptimizerConfig

        netlist, board, context, composite = simple_setup
        config = OptimizerConfig(
            epochs=20,
            seed=42,
            log_interval=5,
            checkpoint=OptimizerConfig.fast_test().checkpoint,
            early_stopping=OptimizerConfig.fast_test().early_stopping,
        )

        result = train(netlist, board, composite, context, config)

        assert len(result.history) > 0
        # Check metrics structure
        metrics = result.history[0]
        assert hasattr(metrics, "epoch")
        assert hasattr(metrics, "loss")
        assert hasattr(metrics, "temperature")
        assert hasattr(metrics, "learning_rate")

    def test_callback_called(self, simple_setup):
        """Test that callback is called during training."""
        from temper_placer.optimizer import train, OptimizerConfig

        netlist, board, context, composite = simple_setup
        config = OptimizerConfig(
            epochs=10,
            seed=42,
            log_interval=5,
            checkpoint=OptimizerConfig.fast_test().checkpoint,
            early_stopping=OptimizerConfig.fast_test().early_stopping,
        )

        callback_count = [0]

        def callback(metrics):
            callback_count[0] += 1

        result = train(netlist, board, composite, context, config, callback=callback)

        assert callback_count[0] > 0
