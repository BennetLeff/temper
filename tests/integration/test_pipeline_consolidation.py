"""
Integration tests for pipeline consolidation.

These tests ensure that the consolidated create_drc_aware_pipeline()
includes CourtyardCheckStage and produces correct results equivalent
to the original MVP3Runner.
"""

import pytest
from pathlib import Path
from temper_placer.io.kicad_metadata import (
    extract_kicad_metadata,
    KiCadMetadata,
    PadSize,
)
from temper_placer.deterministic.geometry.courtyard import Courtyard
from temper_placer.deterministic import create_drc_aware_pipeline, BoardState
from temper_placer.deterministic.stages import (
    CourtyardCheckStage,
    ApplyPlacementsStage,
    ClearanceGridStage,
)
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.config_loader import load_constraints, constraints_to_design_rules


@pytest.fixture
def temper_pcb_path():
    """Path to the Temper PCB file."""
    repo_root = Path(__file__).parent.parent.parent
    pcb_path = repo_root / "pcb" / "temper.kicad_pcb"
    if not pcb_path.exists():
        pytest.skip(f"Temper PCB not found: {pcb_path}")
    return pcb_path


@pytest.fixture
def temper_config_path():
    """Path to the Temper config file."""
    repo_root = Path(__file__).parent.parent.parent
    config_path = repo_root / "configs" / "temper_deterministic_config.yaml"
    if not config_path.exists():
        pytest.skip(f"Temper config not found: {config_path}")
    return config_path


class TestKiCadMetadataExtraction:
    """Test extraction of typed metadata from KiCad PCB files."""

    def test_extract_kicad_metadata_returns_typed_object(self, temper_pcb_path):
        """Test that extract_kicad_metadata returns a properly typed KiCadMetadata object."""
        metadata = extract_kicad_metadata(temper_pcb_path)

        assert isinstance(metadata, KiCadMetadata)
        assert isinstance(metadata.courtyards, dict)
        assert isinstance(metadata.pad_sizes, dict)
        assert isinstance(metadata.board_width, float)
        assert isinstance(metadata.board_height, float)

    def test_extract_kicad_metadata_extracts_courtyards(self, temper_pcb_path):
        """Test that courtyards are extracted for all components."""
        metadata = extract_kicad_metadata(temper_pcb_path)

        # Should have courtyards for major components
        assert len(metadata.courtyards) > 0

        # Each courtyard should be a Courtyard object
        for ref, courtyard in metadata.courtyards.items():
            assert isinstance(courtyard, Courtyard)
            assert courtyard.component_ref == ref
            assert len(courtyard.points) >= 3  # Valid polygon

            # Points should be tuples of floats
            for point in courtyard.points:
                assert isinstance(point, tuple)
                assert len(point) == 2
                assert isinstance(point[0], float)
                assert isinstance(point[1], float)

    def test_extract_kicad_metadata_extracts_pad_sizes(self, temper_pcb_path):
        """Test that pad sizes are extracted with correct types."""
        metadata = extract_kicad_metadata(temper_pcb_path)

        # Should have pad sizes
        assert len(metadata.pad_sizes) > 0

        # Each pad size should be typed correctly
        for key, pad_size in metadata.pad_sizes.items():
            assert isinstance(key, tuple)
            assert len(key) == 2
            assert isinstance(key[0], str)  # component_ref
            assert isinstance(key[1], str)  # pad_number

            assert isinstance(pad_size, PadSize)
            assert pad_size.component_ref == key[0]
            assert pad_size.pad_number == key[1]
            assert pad_size.width > 0
            assert pad_size.height > 0
            assert isinstance(pad_size.shape, str)

    def test_extract_kicad_metadata_validates_board_dimensions(self, temper_pcb_path):
        """Test that board dimensions are positive and reasonable."""
        metadata = extract_kicad_metadata(temper_pcb_path)

        assert metadata.board_width > 0
        assert metadata.board_height > 0
        # Temper board should be reasonably sized
        assert 50 < metadata.board_width < 200  # mm
        assert 50 < metadata.board_height < 200  # mm

    def test_courtyard_validation_handles_invalid_polygons(self):
        """Test that Courtyard falls back to default square for invalid polygons."""
        # The existing Courtyard class has a fallback for < 3 points
        courtyard = Courtyard(component_ref="U1", points=[(0, 0), (1, 1)])  # Only 2 points
        # Should have fallback square
        assert len(courtyard.points) >= 3

    def test_kicad_metadata_validation_rejects_negative_dimensions(self):
        """Test that KiCadMetadata validation rejects invalid board dimensions."""
        with pytest.raises(ValueError, match="Board dimensions must be positive"):
            KiCadMetadata(
                courtyards={},
                pad_sizes={},
                board_width=-100.0,  # Invalid
                board_height=150.0,
            )


class TestPipelineConsolidation:
    """Test that create_drc_aware_pipeline includes CourtyardCheckStage."""

    def test_create_drc_aware_pipeline_requires_metadata(self, temper_config_path):
        """Test that pipeline requires KiCadMetadata parameter."""
        constraints = load_constraints(temper_config_path)
        design_rules = constraints_to_design_rules(constraints)

        # This should fail because we haven't provided metadata yet
        # (Will fail once we update the signature)
        with pytest.raises(TypeError):
            create_drc_aware_pipeline(design_rules=design_rules, config=constraints)

    def test_create_drc_aware_pipeline_includes_courtyard_stage(
        self, temper_pcb_path, temper_config_path
    ):
        """Test that pipeline includes CourtyardCheckStage when metadata provided."""
        metadata = extract_kicad_metadata(temper_pcb_path)
        constraints = load_constraints(temper_config_path)
        design_rules = constraints_to_design_rules(constraints)

        pipeline = create_drc_aware_pipeline(
            design_rules=design_rules,
            config=constraints,
            metadata=metadata,
        )

        # Pipeline should include CourtyardCheckStage
        stage_names = [stage.name for stage in pipeline.stages]
        assert "courtyard_check" in stage_names

    def test_courtyard_stage_runs_before_clearance_grid(self, temper_pcb_path, temper_config_path):
        """Test that CourtyardCheckStage runs before ClearanceGridStage."""
        metadata = extract_kicad_metadata(temper_pcb_path)
        constraints = load_constraints(temper_config_path)
        design_rules = constraints_to_design_rules(constraints)

        pipeline = create_drc_aware_pipeline(
            design_rules=design_rules,
            config=constraints,
            metadata=metadata,
        )

        stage_names = [stage.name for stage in pipeline.stages]
        courtyard_idx = stage_names.index("courtyard_check")
        clearance_idx = stage_names.index("clearance_grid")

        # Courtyard check must come before clearance grid
        assert courtyard_idx < clearance_idx

    def test_apply_placements_runs_after_courtyard_check(self, temper_pcb_path, temper_config_path):
        """Test that ApplyPlacementsStage runs after CourtyardCheckStage.

        This is DRC-FIX-5: We need to re-apply placements after courtyard
        checking to sync component.initial_position with the clamped positions.
        """
        metadata = extract_kicad_metadata(temper_pcb_path)
        constraints = load_constraints(temper_config_path)
        design_rules = constraints_to_design_rules(constraints)

        pipeline = create_drc_aware_pipeline(
            design_rules=design_rules,
            config=constraints,
            metadata=metadata,
        )

        stage_names = [stage.name for stage in pipeline.stages]
        courtyard_idx = stage_names.index("courtyard_check")

        # Find next ApplyPlacementsStage after courtyard check
        apply_indices = [i for i, name in enumerate(stage_names) if name == "apply_placements"]
        next_apply = [idx for idx in apply_indices if idx > courtyard_idx]

        assert len(next_apply) > 0, "No ApplyPlacementsStage found after CourtyardCheckStage"
        assert next_apply[0] == courtyard_idx + 1, (
            "ApplyPlacementsStage should immediately follow CourtyardCheckStage"
        )

    def test_clearance_grid_receives_pad_sizes(self, temper_pcb_path, temper_config_path):
        """Test that ClearanceGridStage receives pad_sizes from metadata."""
        metadata = extract_kicad_metadata(temper_pcb_path)
        constraints = load_constraints(temper_config_path)
        design_rules = constraints_to_design_rules(constraints)

        pipeline = create_drc_aware_pipeline(
            design_rules=design_rules,
            config=constraints,
            metadata=metadata,
        )

        # Find ClearanceGridStage
        clearance_stage = None
        for stage in pipeline.stages:
            if isinstance(stage, ClearanceGridStage):
                clearance_stage = stage
                break

        assert clearance_stage is not None
        assert hasattr(clearance_stage, "pad_sizes")
        # Should have pad sizes from metadata
        assert len(clearance_stage.pad_sizes) > 0


class TestPipelineEquivalence:
    """Test that consolidated pipeline produces equivalent results to MVP3Runner."""

    def test_consolidated_pipeline_produces_valid_placements(
        self, temper_pcb_path, temper_config_path
    ):
        """Test that pipeline with courtyards produces valid placements."""
        # Extract metadata
        metadata = extract_kicad_metadata(temper_pcb_path)

        # Load config and design rules
        constraints = load_constraints(temper_config_path)
        design_rules = constraints_to_design_rules(constraints)

        # Parse board
        parse_result = parse_kicad_pcb(temper_pcb_path)

        # Create pipeline
        pipeline = create_drc_aware_pipeline(
            design_rules=design_rules,
            config=constraints,
            metadata=metadata,
        )

        # Run pipeline
        initial_state = BoardState(
            board=parse_result.board,
            netlist=parse_result.netlist,
        )
        final_state = pipeline.run(initial_state)

        # Check results
        assert final_state.placements is not None
        assert len(final_state.placements) > 0

        # All placements should be within board bounds (with 5mm margin)
        margin = 5.0  # Same as CourtyardCheckStage default
        for ref, (x, y) in final_state.placements:
            assert margin <= x <= metadata.board_width - margin, (
                f"{ref} x={x} outside bounds [{margin}, {metadata.board_width - margin}]"
            )
            assert margin <= y <= metadata.board_height - margin, (
                f"{ref} y={y} outside bounds [{margin}, {metadata.board_height - margin}]"
            )

    def test_consolidated_pipeline_resolves_overlaps(self, temper_pcb_path, temper_config_path):
        """Test that pipeline resolves courtyard overlaps."""
        # Extract metadata
        metadata = extract_kicad_metadata(temper_pcb_path)

        # Load config and design rules
        constraints = load_constraints(temper_config_path)
        design_rules = constraints_to_design_rules(constraints)

        # Parse board
        parse_result = parse_kicad_pcb(temper_pcb_path)

        # Create pipeline
        pipeline = create_drc_aware_pipeline(
            design_rules=design_rules,
            config=constraints,
            metadata=metadata,
        )

        # Run pipeline
        initial_state = BoardState(
            board=parse_result.board,
            netlist=parse_result.netlist,
        )
        final_state = pipeline.run(initial_state)

        # Check for overlaps using courtyard geometry
        from temper_placer.deterministic.geometry.courtyard import check_overlap

        placements_dict = dict(final_state.placements)
        overlaps = []

        refs = list(placements_dict.keys())
        for i in range(len(refs)):
            ref1 = refs[i]
            if ref1 not in metadata.courtyards:
                continue

            for j in range(i + 1, len(refs)):
                ref2 = refs[j]
                if ref2 not in metadata.courtyards:
                    continue

                if check_overlap(
                    metadata.courtyards[ref1],
                    placements_dict[ref1],
                    0,  # rotation
                    metadata.courtyards[ref2],
                    placements_dict[ref2],
                    0,  # rotation
                ):
                    overlaps.append((ref1, ref2))

        # Should have no overlaps after courtyard resolution
        assert len(overlaps) == 0, f"Found {len(overlaps)} courtyard overlaps: {overlaps[:5]}"
