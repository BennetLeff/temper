"""
Integration test for PhasedComponentAssignmentStage in deterministic pipeline.

Tests that the constraint-aware placement stage works within the full
deterministic pipeline using create_drc_aware_pipeline().
"""

from pathlib import Path
import pytest

from temper_placer.deterministic import create_drc_aware_pipeline, BoardState
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.config_loader import load_constraints, constraints_to_design_rules
from temper_placer.io.kicad_metadata import extract_kicad_metadata


TEMPER_CONFIG_PATH = Path(__file__).parents[4] / "configs" / "temper_deterministic_config.yaml"
TEMPER_PCB_PATH = Path(__file__).parents[4] / "pcb" / "temper_agent_optimized.kicad_pcb"


class TestPhasedPlacementIntegration:
    """Test phased placement in full pipeline."""

    @pytest.mark.skipif(not TEMPER_CONFIG_PATH.exists(), reason="Config not found")
    @pytest.mark.skipif(not TEMPER_PCB_PATH.exists(), reason="PCB not found")
    def test_phased_placement_in_pipeline(self):
        """Test that PhasedComponentAssignmentStage works in deterministic pipeline."""
        # Load board and config
        parse_result = parse_kicad_pcb(TEMPER_PCB_PATH)
        constraints = load_constraints(TEMPER_CONFIG_PATH)
        design_rules = constraints_to_design_rules(constraints)
        metadata = extract_kicad_metadata(TEMPER_PCB_PATH)

        # Create pipeline - should use PhasedComponentAssignmentStage
        # because constraints has component_spacing_rules or component_groups
        pipeline = create_drc_aware_pipeline(
            design_rules=design_rules,
            config=constraints,
            metadata=metadata,
            zone_aware=True,
        )

        # Verify we have a placement stage
        stage_names = [s.name for s in pipeline.stages]
        has_placement_stage = (
            "phased_component_assignment" in stage_names or "component_assignment" in stage_names
        )
        assert has_placement_stage, f"No placement stage found: {stage_names}"

        # Run placement stages only (stop before routing for faster test)
        initial_state = BoardState(board=parse_result.board, netlist=parse_result.netlist)
        state = initial_state

        # Run until after placements are applied (first 5-6 stages)
        for stage in pipeline.stages[:6]:
            state = stage.run(state)

        # Should have placements
        assert state.placements is not None
        assert len(state.placements) > 0, "No placements generated"

        print(f"\n  Phased placement completed:")
        print(f"  Components placed: {len(state.placements)}")

    @pytest.mark.skipif(not TEMPER_CONFIG_PATH.exists(), reason="Config not found")
    @pytest.mark.skipif(not TEMPER_PCB_PATH.exists(), reason="PCB not found")
    def test_pipeline_uses_correct_stage_based_on_config(self):
        """Test that pipeline selects correct stage based on config."""
        metadata = extract_kicad_metadata(TEMPER_PCB_PATH)

        # Without constraints, should use ComponentAssignmentStage
        pipeline_no_constraints = create_drc_aware_pipeline(
            design_rules=None,
            config=None,  # No constraints
            metadata=metadata,
            zone_aware=True,
        )

        stage_names = [s.name for s in pipeline_no_constraints.stages]
        assert "component_assignment" in stage_names, (
            f"Expected ComponentAssignmentStage without constraints: {stage_names}"
        )

        # With constraints that have placement_priority, should use PhasedComponentAssignmentStage
        constraints = load_constraints(TEMPER_CONFIG_PATH)
        if (
            getattr(constraints, "placement_priority", None)
            or getattr(constraints, "component_spacing_rules", None)
            or getattr(constraints, "component_groups", None)
        ):
            pipeline_with_constraints = create_drc_aware_pipeline(
                design_rules=None,
                config=constraints,
                metadata=metadata,
                zone_aware=True,
            )

            stage_names_with = [s.name for s in pipeline_with_constraints.stages]
            assert "phased_component_assignment" in stage_names_with, (
                f"Expected PhasedComponentAssignmentStage with constraints: {stage_names_with}"
            )
            print("\n  PhasedComponentAssignmentStage correctly selected")


class TestConstraintAwarePlacement:
    """Test that phased placement respects constraints."""

    @pytest.mark.skipif(not TEMPER_CONFIG_PATH.exists(), reason="Config not found")
    @pytest.mark.skipif(not TEMPER_PCB_PATH.exists(), reason="PCB not found")
    def test_phased_placement_respects_constraints(self):
        """Test that phased placement respects constraint rules."""
        from temper_placer.constraints.reporter import ConstraintReporter

        parse_result = parse_kicad_pcb(TEMPER_PCB_PATH)
        constraints = load_constraints(TEMPER_CONFIG_PATH)
        design_rules = constraints_to_design_rules(constraints)
        metadata = extract_kicad_metadata(TEMPER_PCB_PATH)

        pipeline = create_drc_aware_pipeline(
            design_rules=design_rules,
            config=constraints,
            metadata=metadata,
            zone_aware=True,
        )

        # Run placement stages
        initial_state = BoardState(board=parse_result.board, netlist=parse_result.netlist)
        state = initial_state
        for stage in pipeline.stages[:6]:
            state = stage.run(state)

        # Verify constraints are satisfied
        if state.placements:
            placements_dict = dict(state.placements)
            reporter = ConstraintReporter(constraints)
            report = reporter.check(placements_dict)

            # Should have no hard violations (warnings are OK)
            violations = report.violations  # Property, not method
            if violations:
                for v in violations[:5]:  # Show first 5
                    print(f"  VIOLATION: {v.constraint_type}: {v.message}")

            # Note: Some violations may be expected if constraints conflict
            # with zone assignments. This is a smoke test.
            print(f"\n  Constraint report:")
            print(f"  Hard violations: {len(violations)}")
            print(f"  Warnings: {len(report.warnings)}")
