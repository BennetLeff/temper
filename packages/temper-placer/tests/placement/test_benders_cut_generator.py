"""
Tests for Benders Cut Generator.

The cut generator converts blocking components (from min-cut analysis)
into ILP constraints for the Master Problem.
"""

import pytest
from temper_placer.placement.benders_cut_generator import (
    BendersCutGenerator,
    RoutabilityCut,
    CutType,
)
from temper_placer.placement.benders_mincut_mapper import (
    BlockingComponent,
    CutDirection,
)


class TestBendersCutGenerator:
    """Test suite for cut generation."""

    @pytest.fixture
    def generator(self):
        """Create a cut generator instance."""
        return BendersCutGenerator()

    def test_horizontal_pair_cut(self, generator):
        """Test generating a cut for a horizontal component pair."""
        blocking = [
            BlockingComponent(
                component_ref="U1",
                direction=CutDirection.HORIZONTAL,
                position=(20.0, 20.0),
                edges_involved=2,
            ),
            BlockingComponent(
                component_ref="U2",
                direction=CutDirection.HORIZONTAL,
                position=(40.0, 20.0),
                edges_involved=2,
            ),
        ]

        cuts = generator.generate_cuts(blocking)

        assert len(cuts) > 0, "Should generate at least one cut"
        cut = cuts[0]

        assert cut.cut_type == CutType.HORIZONTAL
        assert len(cut.component_pair) == 2
        assert set(cut.component_pair) == {"U1", "U2"}
        assert cut.gap_required > 0, "Gap should be positive"

    def test_vertical_pair_cut(self, generator):
        """Test generating a cut for a vertical component pair."""
        blocking = [
            BlockingComponent(
                component_ref="U1",
                direction=CutDirection.VERTICAL,
                position=(20.0, 20.0),
                edges_involved=1,
            ),
            BlockingComponent(
                component_ref="U3",
                direction=CutDirection.VERTICAL,
                position=(20.0, 40.0),
                edges_involved=1,
            ),
        ]

        cuts = generator.generate_cuts(blocking)

        assert len(cuts) > 0
        cut = cuts[0]

        assert cut.cut_type == CutType.VERTICAL
        assert set(cut.component_pair) == {"U1", "U3"}
        assert cut.gap_required > 0

    def test_multiple_cuts(self, generator):
        """Test generating multiple cuts from complex blocking scenario."""
        blocking = [
            # Horizontal blockers
            BlockingComponent("U1", CutDirection.HORIZONTAL, (10.0, 20.0), 1),
            BlockingComponent("U2", CutDirection.HORIZONTAL, (30.0, 20.0), 1),
            BlockingComponent("U3", CutDirection.HORIZONTAL, (50.0, 20.0), 1),
            # Vertical blockers
            BlockingComponent("U4", CutDirection.VERTICAL, (20.0, 10.0), 1),
            BlockingComponent("U5", CutDirection.VERTICAL, (20.0, 30.0), 1),
        ]

        cuts = generator.generate_cuts(blocking)

        # Should generate cuts for both horizontal and vertical pairs
        assert len(cuts) >= 2
        h_cuts = [c for c in cuts if c.cut_type == CutType.HORIZONTAL]
        v_cuts = [c for c in cuts if c.cut_type == CutType.VERTICAL]
        assert len(h_cuts) > 0
        assert len(v_cuts) > 0

    def test_gap_estimation_based_on_congestion(self, generator):
        """Test that gap size reflects congestion level."""
        # Light congestion
        light_blocking = [
            BlockingComponent("U1", CutDirection.HORIZONTAL, (20.0, 20.0), 1),
            BlockingComponent("U2", CutDirection.HORIZONTAL, (40.0, 20.0), 1),
        ]

        # Heavy congestion
        heavy_blocking = [
            BlockingComponent("U1", CutDirection.HORIZONTAL, (20.0, 20.0), 5),
            BlockingComponent("U2", CutDirection.HORIZONTAL, (40.0, 20.0), 5),
        ]

        light_cuts = generator.generate_cuts(light_blocking)
        heavy_cuts = generator.generate_cuts(heavy_blocking)

        # Heavy congestion should require larger gap
        if len(light_cuts) > 0 and len(heavy_cuts) > 0:
            assert heavy_cuts[0].gap_required >= light_cuts[0].gap_required

    def test_empty_blocking_list(self, generator):
        """Test that empty blocking list returns no cuts."""
        cuts = generator.generate_cuts([])
        assert len(cuts) == 0

    def test_single_blocking_component(self, generator):
        """Test that single blocker doesn't generate cuts (need pairs)."""
        blocking = [
            BlockingComponent("U1", CutDirection.HORIZONTAL, (20.0, 20.0), 1),
        ]

        cuts = generator.generate_cuts(blocking)
        # Single component can't form a pair, so no cuts
        assert len(cuts) == 0

    def test_cut_data_structure(self, generator):
        """Test that RoutabilityCut has correct fields."""
        blocking = [
            BlockingComponent("U1", CutDirection.HORIZONTAL, (20.0, 20.0), 2),
            BlockingComponent("U2", CutDirection.HORIZONTAL, (40.0, 20.0), 2),
        ]

        cuts = generator.generate_cuts(blocking)
        cut = cuts[0]

        assert hasattr(cut, "cut_type")
        assert hasattr(cut, "component_pair")
        assert hasattr(cut, "gap_required")
        assert hasattr(cut, "iteration")
        assert isinstance(cut.cut_type, CutType)
        assert isinstance(cut.component_pair, tuple)
        assert len(cut.component_pair) == 2
        assert isinstance(cut.gap_required, float)
        assert isinstance(cut.iteration, int)


class TestCutTypeEnum:
    """Test CutType enum."""

    def test_cut_types_exist(self):
        """Test that both cut types are defined."""
        assert hasattr(CutType, "HORIZONTAL")
        assert hasattr(CutType, "VERTICAL")

    def test_cut_type_conversion(self):
        """Test conversion between CutDirection and CutType."""
        from temper_placer.placement.benders_cut_generator import direction_to_cut_type

        assert direction_to_cut_type(CutDirection.HORIZONTAL) == CutType.HORIZONTAL
        assert direction_to_cut_type(CutDirection.VERTICAL) == CutType.VERTICAL


class TestCutApplication:
    """Test applying cuts to BendersMasterProblem."""

    def test_cut_compatible_with_master_problem(self):
        """Test that generated cuts are compatible with Master Problem interface."""
        generator = BendersCutGenerator()
        blocking = [
            BlockingComponent("U1", CutDirection.HORIZONTAL, (20.0, 20.0), 2),
            BlockingComponent("U2", CutDirection.HORIZONTAL, (40.0, 20.0), 2),
        ]

        cuts = generator.generate_cuts(blocking)
        cut = cuts[0]

        # Check compatibility with add_routability_cut() signature
        # Expected: cut_type (str), components (list), gap_required (float)
        assert cut.cut_type in (CutType.HORIZONTAL, CutType.VERTICAL)
        assert len(cut.component_pair) == 2
        assert cut.gap_required > 0


class TestIntegrationWithMapper:
    """Integration tests with MinCutMapper."""

    def test_end_to_end_mincut_to_cut(self):
        """Test complete flow from min-cut edges to ILP cuts."""
        from temper_placer.placement.benders_mincut_mapper import MinCutMapper

        # Create simple layout
        components = [
            type(
                "ComponentData",
                (),
                {
                    "ref": "U1",
                    "width_mm": 10.0,
                    "height_mm": 5.0,
                    "x_mm": 20.0,
                    "y_mm": 20.0,
                    "classification": "FREE",
                },
            ),
            type(
                "ComponentData",
                (),
                {
                    "ref": "U2",
                    "width_mm": 10.0,
                    "height_mm": 5.0,
                    "x_mm": 40.0,
                    "y_mm": 20.0,
                    "classification": "FREE",
                },
            ),
        ]

        mapper = MinCutMapper(components, tolerance_mm=2.0)
        generator = BendersCutGenerator()

        # Min-cut edge
        min_cut_edges = [
            (("F.Cu", (30.0, 15.0)), ("F.Cu", (30.0, 25.0)), 0),
        ]

        # Map to components
        blocking = mapper.map_mincut_to_components(min_cut_edges)

        # Generate cuts
        cuts = generator.generate_cuts(blocking)

        assert len(cuts) > 0, "Should generate cuts from min-cut analysis"
        assert cuts[0].cut_type == CutType.HORIZONTAL

    def test_temper_board_cut_generation(self):
        """Test cut generation for Temper board scenario."""
        from temper_placer.placement.benders_mincut_mapper import MinCutMapper

        components = [
            type(
                "ComponentData",
                (),
                {
                    "ref": "Q1",
                    "width_mm": 14.4,
                    "height_mm": 3.5,
                    "x_mm": 25.45,
                    "y_mm": 15.0,
                    "classification": "HV",
                },
            ),
            type(
                "ComponentData",
                (),
                {
                    "ref": "Q2",
                    "width_mm": 14.4,
                    "height_mm": 3.5,
                    "x_mm": 50.45,
                    "y_mm": 15.0,
                    "classification": "HV",
                },
            ),
            type(
                "ComponentData",
                (),
                {
                    "ref": "U_GATE",
                    "width_mm": 11.0,
                    "height_mm": 9.49,
                    "x_mm": 35.0,
                    "y_mm": 30.0,
                    "classification": "HV",
                },
            ),
        ]

        mapper = MinCutMapper(components, tolerance_mm=2.0)
        generator = BendersCutGenerator()

        # Vertical barrier between Q1 and Q2
        min_cut_edges = [
            (("F.Cu", (37.5, 10.0)), ("F.Cu", (37.5, 20.0)), 0),
        ]

        blocking = mapper.map_mincut_to_components(min_cut_edges)
        cuts = generator.generate_cuts(blocking)

        assert len(cuts) > 0
        # Should generate horizontal separation between Q1 and Q2
        refs = {c.component_pair[0] for c in cuts} | {c.component_pair[1] for c in cuts}
        assert refs & {"Q1", "Q2", "U_GATE"}
