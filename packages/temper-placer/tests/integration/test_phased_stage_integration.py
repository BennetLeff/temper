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

        print(f"\n  Created PhasedComponentAssignmentStage")
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
        assert stage.compiler is not None
        assert stage.slot_filter is not None
        assert stage.slot_scorer is not None

        print(f"\n  Stage ready with constraint compiler")


class TestPhasedStageInPipeline:
    """Test using PhasedComponentAssignmentStage in pipeline context."""

    @pytest.mark.skipif(not TEMPER_CONFIG_PATH.exists(), reason="Config not found")
    def test_import_in_deterministic_module(self):
        """Test that stage can be imported from deterministic module."""
        try:
            from temper_placer.deterministic import create_drc_aware_pipeline
            from temper_placer.deterministic.stages import PhasedComponentAssignmentStage

            # Should be importable
            assert create_drc_aware_pipeline is not None
            assert PhasedComponentAssignmentStage is not None

            print(f"\n  All imports successful")

        except ImportError as e:
            pytest.fail(f"Import failed: {e}")

    @pytest.mark.skipif(not TEMPER_CONFIG_PATH.exists(), reason="Config not found")
    def test_pipeline_selects_phased_stage_when_constraints_present(self):
        """Test that create_drc_aware_pipeline() uses PhasedComponentAssignmentStage with constraints."""
        from temper_placer.deterministic import create_drc_aware_pipeline
        from temper_placer.io.kicad_metadata import extract_kicad_metadata

        constraints = load_constraints(TEMPER_CONFIG_PATH)

        # Need metadata to create pipeline
        pcb_path = Path(__file__).parents[4] / "pcb" / "temper_agent_optimized.kicad_pcb"
        if not pcb_path.exists():
            pytest.skip("PCB file not found")

        metadata = extract_kicad_metadata(pcb_path)

        # With constraints that have spacing rules or groups, should use PhasedComponentAssignmentStage
        if (
            getattr(constraints, "placement_priority", None)
            or getattr(constraints, "component_spacing_rules", None)
            or getattr(constraints, "component_groups", None)
        ):
            pipeline = create_drc_aware_pipeline(
                design_rules=None,
                config=constraints,
                metadata=metadata,
            )

            stage_names = [s.name for s in pipeline.stages]
            assert "phased_component_assignment" in stage_names, (
                f"Expected PhasedComponentAssignmentStage with constraints: {stage_names}"
            )

            print(f"\n  PhasedComponentAssignmentStage correctly selected")
        else:
            pytest.skip("Config has no constraint rules")
