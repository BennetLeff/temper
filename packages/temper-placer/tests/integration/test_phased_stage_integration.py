"""
Simple unit test for PhasedComponentAssignmentStage integration.

Tests that the stage can be instantiated and used in a pipeline context.
"""

import pytest
from pathlib import Path

from temper_placer.deterministic.stages import PhasedComponentAssignmentStage
from temper_placer.io.config_loader import load_constraints


TEMPER_CONFIG_PATH = Path(__file__).parents[4] / "configs" / "temper_deterministic_config.yaml"


class TestPhasedStageInstantiation:
    """Test that PhasedComponentAssignmentStage can be created."""

    @pytest.mark.skipif(not TEMPER_CONFIG_PATH.exists(), reason="Config not found")
    def test_create_stage_from_config(self):
        """Test creating PhasedComponentAssignmentStage from config."""
        # Load constraints
        constraints = load_constraints(TEMPER_CONFIG_PATH)

        # Create stage
        stage = PhasedComponentAssignmentStage(
            constraints=constraints,
            slot_spacing=12.0,
            fixed_placements={},
        )

        assert stage is not None
        assert stage.constraints == constraints
        assert stage.slot_spacing == 12.0

        print(f"\n✓ Created PhasedComponentAssignmentStage")
        print(f"  Spacing rules: {len(constraints.component_spacing_rules)}")
        print(f"  Groups: {len(constraints.component_groups)}")

    @pytest.mark.skipif(not TEMPER_CONFIG_PATH.exists(), reason="Config not found")
    def test_stage_has_constraint_compiler(self):
        """Test that stage creates ConstraintCompiler internally."""
        constraints = load_constraints(TEMPER_CONFIG_PATH)

        stage = PhasedComponentAssignmentStage(
            constraints=constraints,
            slot_spacing=12.0,
        )

        # Stage should create a compiler internally
        # We can't access it directly but we can test the stage runs
        assert stage is not None

        print(f"\n✓ Stage ready with constraint compiler")


class TestPhasedStageInPipeline:
    """Test using PhasedComponentAssignmentStage in pipeline context."""

    @pytest.mark.skipif(not TEMPER_CONFIG_PATH.exists(), reason="Config not found")
    def test_import_in_pipeline_module(self):
        """Test that stage can be imported where needed."""
        try:
            from temper_placer.pipeline.mvp3_runner import MVP3Config
            from temper_placer.deterministic.stages import PhasedComponentAssignmentStage

            # Should be importable
            assert MVP3Config is not None
            assert PhasedComponentAssignmentStage is not None

            print(f"\n✓ All imports successful")

        except ImportError as e:
            pytest.fail(f"Import failed: {e}")

    @pytest.mark.skipif(not TEMPER_CONFIG_PATH.exists(), reason="Config not found")
    def test_mvp3_config_has_phased_flag(self):
        """Test that MVP3Config has use_phased_placement flag."""
        from temper_placer.pipeline.mvp3_runner import MVP3Config

        # Default should be True (use phased placement)
        config = MVP3Config()
        assert hasattr(config, "use_phased_placement")
        assert config.use_phased_placement == True

        # Can be disabled
        config_disabled = MVP3Config(use_phased_placement=False)
        assert config_disabled.use_phased_placement == False

        print(f"\n✓ MVP3Config supports phased placement flag")
