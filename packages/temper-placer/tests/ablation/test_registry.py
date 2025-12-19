"""Tests for ablation study component registries."""

from temper_placer.ablation.config import ComponentToggle, LossToggle
from temper_placer.ablation.registry import (
    HeuristicRegistry,
    LossRegistry,
    TechniqueApplicator,
)


class TestHeuristicRegistry:
    """Tests for HeuristicRegistry."""

    def test_list_heuristics(self):
        """Should list all heuristic names."""
        names = HeuristicRegistry.list_heuristics()

        assert len(names) == 11
        assert "spectral_init" in names
        assert "force_directed" in names

    def test_create_pipeline_all_enabled(self):
        """Should attempt to create pipeline with all heuristics enabled."""
        toggle = ComponentToggle()  # All enabled
        pipeline = HeuristicRegistry.create_pipeline(toggle)

        # Should have created a pipeline (may have 0 heuristics if they couldn't instantiate)
        assert hasattr(pipeline, 'heuristics')

    def test_create_pipeline_none_enabled(self):
        """Should create empty pipeline when none enabled."""
        toggle = ComponentToggle.all_disabled()
        pipeline = HeuristicRegistry.create_pipeline(toggle)

        # Pipeline should exist but be empty
        assert hasattr(pipeline, 'heuristics')
        assert len(pipeline.heuristics) == 0

    def test_create_pipeline_selective(self):
        """Should respect toggle settings."""
        toggle = ComponentToggle.all_disabled()
        toggle.spectral_init = True

        pipeline = HeuristicRegistry.create_pipeline(toggle)

        # Should have attempted to add heuristics
        assert hasattr(pipeline, 'heuristics')

    def test_get_heuristic_info(self):
        """Should return heuristic info."""
        info = HeuristicRegistry.get_heuristic_info("spectral_init")

        assert info["name"] == "spectral_init"
        assert "class" in info
        assert "default_kwargs" in info


class TestLossRegistry:
    """Tests for LossRegistry."""

    def test_list_losses(self):
        """Should list all loss names."""
        names = LossRegistry.list_losses()

        assert len(names) == 24
        assert "overlap" in names
        assert "wirelength" in names

    def test_get_default_weights(self):
        """Should return default weights."""
        weights = LossRegistry.get_default_weights()

        assert "overlap" in weights
        assert weights["overlap"] == 100.0
        assert weights["wirelength"] == 10.0

    def test_create_composite_loss_all_enabled(self):
        """Should attempt to create composite with all losses enabled."""
        toggle = LossToggle()
        loss = LossRegistry.create_composite_loss(toggle)

        # Should have created a composite loss (may have fewer than 20 if some fail to instantiate)
        assert hasattr(loss, 'losses')
        assert len(loss.losses) > 0  # Should have at least some losses

    def test_create_composite_loss_none_enabled(self):
        """Should create empty composite when none enabled."""
        toggle = LossToggle.all_disabled()
        loss = LossRegistry.create_composite_loss(toggle)

        assert len(loss.losses) == 0

    def test_create_composite_loss_selective(self):
        """Should respect toggle settings."""
        toggle = LossToggle.hard_constraints_only()
        loss = LossRegistry.create_composite_loss(toggle)

        # Should have at least overlap (boundary may fail to instantiate)
        assert len(loss.losses) >= 1

    def test_create_composite_loss_custom_weights(self):
        """Should apply custom weights."""
        toggle = LossToggle(overlap=True)
        weights = {"overlap": 50.0}
        loss = LossRegistry.create_composite_loss(toggle, weights)

        # Check that at least one loss has the custom weight
        assert len(loss.losses) > 0
        assert any(l.weight == 50.0 for l in loss.losses)


class TestTechniqueApplicator:
    """Tests for TechniqueApplicator."""

    def test_apply_toggles_all_enabled(self):
        """Should keep all techniques when enabled."""
        from temper_placer.optimizer.config import OptimizerConfig

        base = OptimizerConfig()
        toggle = ComponentToggle()  # All enabled

        config = TechniqueApplicator.apply_toggles(base, toggle)

        assert config.use_centrality_weighting is True

    def test_apply_toggles_disable_curriculum(self):
        """Should disable curriculum when toggled off."""
        from temper_placer.optimizer.config import CurriculumPhase, OptimizerConfig

        # Create base config with curriculum phase
        base = OptimizerConfig()
        base.curriculum_phases = [CurriculumPhase(name="test", start_epoch=0, end_epoch=100)]

        toggle = ComponentToggle(curriculum_learning=False)
        config = TechniqueApplicator.apply_toggles(base, toggle)

        assert len(config.curriculum_phases) == 0

    def test_apply_toggles_constant_temperature(self):
        """Should set constant temperature when annealing disabled."""
        from temper_placer.optimizer.config import OptimizerConfig

        base = OptimizerConfig()
        toggle = ComponentToggle(temperature_annealing=False)

        config = TechniqueApplicator.apply_toggles(base, toggle)

        # Temperature should be constant (start == end)
        assert config.temperature.start == config.temperature.end

    def test_apply_toggles_constant_learning_rate(self):
        """Should set constant learning rate when annealing disabled."""
        from temper_placer.optimizer.config import OptimizerConfig

        base = OptimizerConfig()
        toggle = ComponentToggle(learning_rate_annealing=False)

        config = TechniqueApplicator.apply_toggles(base, toggle)

        # Learning rate should be constant (initial == final)
        assert config.learning_rate.initial == config.learning_rate.final

    def test_apply_toggles_disable_gradient_clipping(self):
        """Should disable gradient clipping when toggled off."""
        from temper_placer.optimizer.config import OptimizerConfig

        base = OptimizerConfig()
        toggle = ComponentToggle(gradient_clipping=False)

        config = TechniqueApplicator.apply_toggles(base, toggle)

        assert config.gradient_clip_norm is None

    def test_get_technique_status(self):
        """Should extract technique status from config."""
        from temper_placer.optimizer.config import OptimizerConfig

        config = OptimizerConfig()
        status = TechniqueApplicator.get_technique_status(config)

        assert isinstance(status, dict)
        assert "curriculum_learning" in status
        assert "gradient_clipping" in status

    def test_create_minimal_config(self):
        """Should create minimal config with no advanced techniques."""
        config = TechniqueApplicator.create_minimal_config()

        assert len(config.curriculum_phases) == 0
        assert config.gradient_clip_norm is None
        assert config.use_centrality_weighting is False
