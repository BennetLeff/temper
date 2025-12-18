"""Tests for ablation study configuration dataclasses."""

import pytest
from pathlib import Path
from temper_placer.ablation.config import (
    ComponentToggle,
    LossToggle,
    ExperimentConfig,
    AblationStudyConfig,
    HyperparameterOverrides,
)


class TestComponentToggle:
    """Tests for ComponentToggle dataclass."""

    def test_defaults_all_true(self):
        """All fields should default to True."""
        toggle = ComponentToggle()

        # Heuristics
        assert toggle.spectral_init is True
        assert toggle.force_directed is True
        assert toggle.connector_edge_snap is True
        assert toggle.thermal_edge is True
        assert toggle.critical_loop is True
        assert toggle.functional_clustering is True
        assert toggle.power_flow_topology is True
        assert toggle.decoupling_cap is True
        assert toggle.domain_separation is True
        assert toggle.star_ground is True
        assert toggle.signal_flow is True

        # Techniques
        assert toggle.curriculum_learning is True
        assert toggle.gumbel_softmax_rotation is True
        assert toggle.adaptive_overlap_weighting is True
        assert toggle.stochastic_perturbation is True
        assert toggle.centrality_gradient_scaling is True
        assert toggle.temperature_annealing is True
        assert toggle.learning_rate_annealing is True
        assert toggle.gradient_clipping is True

    def test_get_enabled_heuristics(self):
        """Should return list of enabled heuristic names."""
        toggle = ComponentToggle()
        enabled = toggle.get_enabled_heuristics()

        assert len(enabled) == 11
        assert "spectral_init" in enabled
        assert "force_directed" in enabled

    def test_get_enabled_heuristics_with_disabled(self):
        """Should only return enabled heuristics."""
        toggle = ComponentToggle(spectral_init=False, force_directed=False)
        enabled = toggle.get_enabled_heuristics()

        assert len(enabled) == 9
        assert "spectral_init" not in enabled
        assert "force_directed" not in enabled

    def test_get_enabled_techniques(self):
        """Should return list of enabled technique names."""
        toggle = ComponentToggle()
        enabled = toggle.get_enabled_techniques()

        assert len(enabled) == 8
        assert "curriculum_learning" in enabled
        assert "adaptive_overlap_weighting" in enabled

    def test_get_enabled_techniques_with_disabled(self):
        """Should only return enabled techniques."""
        toggle = ComponentToggle(curriculum_learning=False)
        enabled = toggle.get_enabled_techniques()

        assert len(enabled) == 7
        assert "curriculum_learning" not in enabled

    def test_count_enabled(self):
        """Should return tuple of (heuristics, techniques) counts."""
        toggle = ComponentToggle()
        h, t = toggle.count_enabled()

        assert h == 11
        assert t == 8

    def test_count_enabled_with_disabled(self):
        """Should count only enabled components."""
        toggle = ComponentToggle(
            spectral_init=False,
            force_directed=False,
            curriculum_learning=False
        )
        h, t = toggle.count_enabled()

        assert h == 9
        assert t == 7

    def test_to_dict(self):
        """Should convert to dictionary."""
        toggle = ComponentToggle(spectral_init=False)
        d = toggle.to_dict()

        assert isinstance(d, dict)
        assert d["spectral_init"] is False
        assert d["force_directed"] is True

    def test_from_dict(self):
        """Should create from dictionary."""
        data = {
            "spectral_init": False,
            "force_directed": True,
            "curriculum_learning": False,
        }
        toggle = ComponentToggle.from_dict(data)

        assert toggle.spectral_init is False
        assert toggle.force_directed is True
        assert toggle.curriculum_learning is False

    def test_serialization_roundtrip(self):
        """Should survive serialization roundtrip."""
        original = ComponentToggle(
            spectral_init=False,
            curriculum_learning=False,
            gradient_clipping=False
        )
        d = original.to_dict()
        restored = ComponentToggle.from_dict(d)

        assert restored.spectral_init == original.spectral_init
        assert restored.curriculum_learning == original.curriculum_learning
        assert restored.gradient_clipping == original.gradient_clipping

    def test_all_disabled(self):
        """all_disabled() should create toggle with all False."""
        toggle = ComponentToggle.all_disabled()
        h, t = toggle.count_enabled()

        assert h == 0
        assert t == 0


class TestLossToggle:
    """Tests for LossToggle dataclass."""

    def test_defaults_all_true(self):
        """All loss fields should default to True."""
        toggle = LossToggle()

        assert toggle.overlap is True
        assert toggle.boundary is True
        assert toggle.clearance is True
        assert toggle.wirelength is True
        assert toggle.loop_area is True
        assert toggle.thermal is True
        assert toggle.zone is True

    def test_get_enabled_losses(self):
        """Should return list of enabled loss names."""
        toggle = LossToggle()
        enabled = toggle.get_enabled_losses()

        assert len(enabled) == 24
        assert "overlap" in enabled
        assert "wirelength" in enabled

    def test_get_enabled_losses_with_disabled(self):
        """Should only return enabled losses."""
        toggle = LossToggle(overlap=False, wirelength=False)
        enabled = toggle.get_enabled_losses()

        assert len(enabled) == 22
        assert "overlap" not in enabled
        assert "wirelength" not in enabled

    def test_count_enabled(self):
        """Should return count of enabled losses."""
        toggle = LossToggle()
        count = toggle.count_enabled()

        assert count == 24

    def test_count_enabled_with_disabled(self):
        """Should count only enabled losses."""
        toggle = LossToggle(overlap=False, boundary=False)
        count = toggle.count_enabled()

        assert count == 22

    def test_get_by_category(self):
        """Should return losses grouped by category."""
        toggle = LossToggle()
        by_cat = toggle.get_by_category()

        assert "hard_constraints" in by_cat
        assert "design_rules" in by_cat
        assert "performance" in by_cat
        assert "regularization" in by_cat
        assert "domain_specific" in by_cat

    def test_get_by_category_respects_toggles(self):
        """Categories should only include enabled losses."""
        toggle = LossToggle(overlap=False, boundary=False)
        by_cat = toggle.get_by_category()

        assert "overlap" not in by_cat["hard_constraints"]
        assert "boundary" not in by_cat["hard_constraints"]
        assert "clearance" in by_cat["hard_constraints"]

    def test_hard_constraints_only(self):
        """hard_constraints_only() should enable only overlap+boundary."""
        toggle = LossToggle.hard_constraints_only()
        enabled = toggle.get_enabled_losses()

        assert "overlap" in enabled
        assert "boundary" in enabled
        assert "wirelength" not in enabled
        assert "thermal" not in enabled

    def test_all_disabled(self):
        """all_disabled() should create toggle with all False."""
        toggle = LossToggle.all_disabled()
        count = toggle.count_enabled()

        assert count == 0

    def test_to_dict(self):
        """Should convert to dictionary."""
        toggle = LossToggle(overlap=False)
        d = toggle.to_dict()

        assert isinstance(d, dict)
        assert d["overlap"] is False
        assert d["boundary"] is True

    def test_serialization_roundtrip(self):
        """Should survive serialization roundtrip."""
        original = LossToggle(
            overlap=False,
            wirelength=False,
            thermal=False
        )
        d = original.to_dict()
        restored = LossToggle.from_dict(d)

        assert restored.overlap == original.overlap
        assert restored.wirelength == original.wirelength
        assert restored.thermal == original.thermal


class TestExperimentConfig:
    """Tests for ExperimentConfig dataclass."""

    def test_basic_config(self):
        """Should create basic experiment config."""
        config = ExperimentConfig(
            name="test_exp",
            description="Test experiment",
        )

        assert config.name == "test_exp"
        assert config.description == "Test experiment"
        assert isinstance(config.components, ComponentToggle)
        assert isinstance(config.losses, LossToggle)

    def test_invalid_name_raises(self):
        """Should reject invalid experiment names."""
        with pytest.raises(ValueError):
            ExperimentConfig(
                name="invalid@name!",
                description="Test",
            )

    def test_config_with_toggles(self):
        """Should support custom component/loss toggles."""
        components = ComponentToggle(spectral_init=False)
        losses = LossToggle(overlap=False)

        config = ExperimentConfig(
            name="custom",
            description="Custom config",
            components=components,
            losses=losses,
        )

        assert config.components.spectral_init is False
        assert config.losses.overlap is False

    def test_config_with_tags(self):
        """Should support tags for filtering."""
        config = ExperimentConfig(
            name="test",
            description="Test",
            tags=["single_ablation", "heuristic"],
        )

        assert "single_ablation" in config.tags
        assert len(config.tags) == 2

    def test_to_dict(self):
        """Should convert to dictionary."""
        config = ExperimentConfig(
            name="test",
            description="Test description",
            tags=["tag1"],
        )
        d = config.to_dict()

        assert d["name"] == "test"
        assert d["description"] == "Test description"
        assert isinstance(d["components"], dict)
        assert isinstance(d["losses"], dict)
        assert "tag1" in d["tags"]

    def test_from_dict(self):
        """Should create from dictionary."""
        data = {
            "name": "test",
            "description": "Test description",
            "components": {"spectral_init": False},
            "losses": {"overlap": False},
            "tags": ["test_tag"],
        }
        config = ExperimentConfig.from_dict(data)

        assert config.name == "test"
        assert config.components.spectral_init is False
        assert config.losses.overlap is False

    def test_get_config_hash(self):
        """Should return consistent hash."""
        config = ExperimentConfig(
            name="test",
            description="Test",
        )
        hash1 = config.get_config_hash()
        hash2 = config.get_config_hash()

        assert hash1 == hash2
        assert len(hash1) == 12

    def test_config_hash_differs_for_different_configs(self):
        """Different configs should have different hashes."""
        config1 = ExperimentConfig(name="test1", description="Test 1")
        config2 = ExperimentConfig(name="test2", description="Test 2")

        assert config1.get_config_hash() != config2.get_config_hash()


class TestAblationStudyConfig:
    """Tests for AblationStudyConfig dataclass."""

    def test_basic_study_config(self):
        """Should create basic study config."""
        exp = ExperimentConfig(name="test", description="Test")
        config = AblationStudyConfig(
            study_name="test_study",
            experiments=[exp],
        )

        assert config.study_name == "test_study"
        assert len(config.experiments) == 1
        assert len(config.seeds) == 5  # Default 5 seeds

    def test_get_total_runs(self):
        """Should calculate total number of runs."""
        exps = [
            ExperimentConfig(name="test1", description="Test 1"),
            ExperimentConfig(name="test2", description="Test 2"),
        ]
        test_cases = [Path("test1.kicad_pcb"), Path("test2.kicad_pcb")]

        config = AblationStudyConfig(
            study_name="test",
            experiments=exps,
            seeds=[42, 123],
            test_cases=test_cases,
        )

        # 2 experiments × 2 seeds × 2 test cases = 8
        assert config.get_total_runs() == 8

    def test_estimate_runtime_hours(self):
        """Should estimate runtime in hours."""
        exp = ExperimentConfig(name="test", description="Test")
        config = AblationStudyConfig(
            study_name="test",
            experiments=[exp],
            seeds=[42, 123, 456],
            test_cases=[Path("test.kicad_pcb")],
            parallel_workers=4,
        )

        # 1 exp × 3 seeds × 1 test = 3 runs
        # 3 runs × 10 min = 30 min total
        # 30 min / 4 workers = 7.5 min = 0.125 hours
        runtime = config.estimate_runtime_hours(minutes_per_run=10)
        assert abs(runtime - 0.125) < 0.01

    def test_filter_experiments(self):
        """Should filter experiments by tags."""
        exps = [
            ExperimentConfig(name="ablate_test", description="Test", tags=["ablation"]),
            ExperimentConfig(name="add_test", description="Test", tags=["addition"]),
            ExperimentConfig(
                name="combo_test", description="Test", tags=["ablation", "combo"]
            ),
        ]
        config = AblationStudyConfig(
            study_name="test",
            experiments=exps,
        )

        filtered = config.filter_experiments(["ablation"])
        assert len(filtered.experiments) == 2
        assert filtered.experiments[0].name == "ablate_test"
        assert filtered.experiments[1].name == "combo_test"

    def test_save_and_load(self, tmp_path):
        """Should save and load configuration."""
        import tempfile

        exp = ExperimentConfig(
            name="test",
            description="Test experiment",
            tags=["test_tag"],
        )
        original = AblationStudyConfig(
            study_name="test_study",
            experiments=[exp],
            seeds=[42, 123],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            original.save(config_path)
            loaded = AblationStudyConfig.load(config_path)

            assert loaded.study_name == original.study_name
            assert len(loaded.experiments) == 1
            assert loaded.experiments[0].name == "test"
            assert loaded.seeds == original.seeds
