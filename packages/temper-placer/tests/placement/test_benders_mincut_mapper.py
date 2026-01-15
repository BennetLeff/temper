"""
Tests for Min-Cut to Component Mapper.

The mapper takes min-cut edges from Max-Flow analysis and identifies
which components are blocking the routing channels.
"""

import pytest
from temper_placer.placement.benders_mincut_mapper import (
    MinCutMapper,
    BlockingComponent,
    CutDirection,
)
from temper_placer.placement.benders_master import ComponentData


class TestMinCutMapper:
    """Test suite for min-cut to component mapping."""

    @pytest.fixture
    def simple_components(self):
        """Create a simple component layout for testing."""
        return [
            ComponentData(
                ref="U1",
                width_mm=10.0,
                height_mm=5.0,
                x_mm=20.0,
                y_mm=20.0,
                classification="FREE",
            ),
            ComponentData(
                ref="U2",
                width_mm=10.0,
                height_mm=5.0,
                x_mm=40.0,
                y_mm=20.0,
                classification="FREE",
            ),
            ComponentData(
                ref="U3",
                width_mm=5.0,
                height_mm=10.0,
                x_mm=30.0,
                y_mm=40.0,
                classification="FREE",
            ),
        ]

    @pytest.fixture
    def mapper(self, simple_components):
        """Create a mapper instance."""
        return MinCutMapper(simple_components, tolerance_mm=1.0)

    def test_horizontal_cut_identification(self, mapper, simple_components):
        """Test that horizontal cuts (blocking left-right flow) are identified."""
        # Simulate a min-cut edge that runs vertically between U1 and U2
        # This blocks horizontal flow
        min_cut_edges = [
            (("F.Cu", (30.0, 15.0)), ("F.Cu", (30.0, 25.0)), 0),  # Vertical edge at x=30
        ]

        result = mapper.map_mincut_to_components(min_cut_edges)

        # Should identify both U1 and U2 as blocking horizontal flow
        assert len(result) > 0
        refs = {b.component_ref for b in result}
        assert "U1" in refs or "U2" in refs
        # Check that direction is horizontal
        assert any(b.direction == CutDirection.HORIZONTAL for b in result)

    def test_vertical_cut_identification(self, mapper, simple_components):
        """Test that vertical cuts (blocking up-down flow) are identified."""
        # Simulate a min-cut edge that runs horizontally
        # This blocks vertical flow
        min_cut_edges = [
            (("F.Cu", (25.0, 30.0)), ("F.Cu", (35.0, 30.0)), 0),  # Horizontal edge at y=30
        ]

        result = mapper.map_mincut_to_components(min_cut_edges)

        # Should identify components near this horizontal barrier
        assert len(result) > 0
        assert any(b.direction == CutDirection.VERTICAL for b in result)

    def test_empty_mincut(self, mapper):
        """Test that empty min-cut returns empty result."""
        result = mapper.map_mincut_to_components([])
        assert len(result) == 0

    def test_tolerance_buffer(self, simple_components):
        """Test that tolerance parameter affects component detection."""
        # Test with small tolerance
        mapper_small = MinCutMapper(simple_components, tolerance_mm=0.5)
        # Test with large tolerance
        mapper_large = MinCutMapper(simple_components, tolerance_mm=5.0)

        # Edge just outside U1's bounding box
        min_cut_edges = [
            (("F.Cu", (26.0, 20.0)), ("F.Cu", (26.0, 25.0)), 0),  # Edge at x=26, U1 ends at x=25
        ]

        result_small = mapper_small.map_mincut_to_components(min_cut_edges)
        result_large = mapper_large.map_mincut_to_components(min_cut_edges)

        # Larger tolerance should detect more components
        assert len(result_large) >= len(result_small)

    def test_blocking_component_data_structure(self, mapper):
        """Test that BlockingComponent contains correct data."""
        min_cut_edges = [
            (("F.Cu", (30.0, 20.0)), ("F.Cu", (35.0, 20.0)), 2),
        ]

        result = mapper.map_mincut_to_components(min_cut_edges)

        if len(result) > 0:
            blocking = result[0]
            assert hasattr(blocking, "component_ref")
            assert hasattr(blocking, "direction")
            assert hasattr(blocking, "position")
            assert isinstance(blocking.component_ref, str)
            assert isinstance(blocking.direction, CutDirection)
            assert isinstance(blocking.position, tuple)
            assert len(blocking.position) == 2

    def test_component_pair_identification(self, mapper, simple_components):
        """Test identifying pairs of components that need separation."""
        # Edge between U1 and U2
        min_cut_edges = [
            (("F.Cu", (30.0, 20.0)), ("F.Cu", (30.0, 25.0)), 0),
        ]

        result = mapper.map_mincut_to_components(min_cut_edges)
        pairs = mapper.get_component_pairs(result)

        # Should identify U1-U2 pair for horizontal separation
        assert len(pairs) > 0
        refs = {(p[0], p[1]) for p in pairs}
        assert ("U1", "U2") in refs or ("U2", "U1") in refs

    def test_multi_layer_support(self, mapper):
        """Test that mapper handles multi-layer min-cuts."""
        # Cuts on different layers
        min_cut_edges = [
            (("F.Cu", (30.0, 20.0)), ("F.Cu", (30.0, 25.0)), 0),
            (("B.Cu", (30.0, 20.0)), ("B.Cu", (30.0, 25.0)), 0),
        ]

        result = mapper.map_mincut_to_components(min_cut_edges)

        # Should aggregate across layers
        assert len(result) > 0


class TestBlockingComponentDataClass:
    """Test the BlockingComponent data structure."""

    def test_creation(self):
        """Test creating a BlockingComponent."""
        blocking = BlockingComponent(
            component_ref="U1",
            direction=CutDirection.HORIZONTAL,
            position=(20.0, 30.0),
            edges_involved=2,
        )
        assert blocking.component_ref == "U1"
        assert blocking.direction == CutDirection.HORIZONTAL
        assert blocking.position == (20.0, 30.0)
        assert blocking.edges_involved == 2

    def test_equality(self):
        """Test BlockingComponent equality."""
        b1 = BlockingComponent(
            component_ref="U1",
            direction=CutDirection.HORIZONTAL,
            position=(20.0, 30.0),
            edges_involved=2,
        )
        b2 = BlockingComponent(
            component_ref="U1",
            direction=CutDirection.HORIZONTAL,
            position=(20.0, 30.0),
            edges_involved=2,
        )
        b3 = BlockingComponent(
            component_ref="U2",
            direction=CutDirection.HORIZONTAL,
            position=(20.0, 30.0),
            edges_involved=2,
        )
        assert b1 == b2
        assert b1 != b3


class TestEdgeGeometry:
    """Test edge-component intersection geometry."""

    def test_point_in_bbox_with_tolerance(self):
        """Test point-in-bounding-box with tolerance."""
        component = ComponentData(
            ref="U1",
            width_mm=10.0,
            height_mm=5.0,
            x_mm=20.0,  # Center at (20, 20)
            y_mm=20.0,
            classification="FREE",
        )
        mapper = MinCutMapper([component], tolerance_mm=1.0)

        # Bounding box: (15, 17.5) to (25, 22.5) + 1mm tolerance = (14, 16.5) to (26, 23.5)
        assert mapper._point_near_bbox((20.0, 20.0), component)  # Center
        assert mapper._point_near_bbox((25.5, 20.0), component)  # Just outside + tolerance
        assert not mapper._point_near_bbox((30.0, 20.0), component)  # Far outside

    def test_edge_intersects_bbox(self):
        """Test edge-bounding box intersection."""
        component = ComponentData(
            ref="U1",
            width_mm=10.0,
            height_mm=5.0,
            x_mm=20.0,
            y_mm=20.0,
            classification="FREE",
        )
        mapper = MinCutMapper([component], tolerance_mm=1.0)

        # Vertical edge through component
        p1 = (20.0, 15.0)
        p2 = (20.0, 25.0)
        assert mapper._edge_intersects_bbox(p1, p2, component)

        # Edge completely outside
        p1 = (30.0, 15.0)
        p2 = (30.0, 25.0)
        assert not mapper._edge_intersects_bbox(p1, p2, component)


class TestIntegrationWithRealData:
    """Integration tests with realistic component layouts."""

    @pytest.fixture
    def temper_layout_subset(self):
        """Create a subset of Temper board layout."""
        return [
            ComponentData(ref="Q1", width_mm=14.4, height_mm=3.5, x_mm=25.45, y_mm=15.0, classification="HV"),
            ComponentData(ref="Q2", width_mm=14.4, height_mm=3.5, x_mm=50.45, y_mm=15.0, classification="HV"),
            ComponentData(ref="U_GATE", width_mm=11.0, height_mm=9.49, x_mm=35.0, y_mm=30.0, classification="HV"),
            ComponentData(ref="C_BUS1", width_mm=10.5, height_mm=3.0, x_mm=28.75, y_mm=60.0, classification="HV"),
        ]

    def test_power_plane_bottleneck(self, temper_layout_subset):
        """Test identifying power plane routing bottleneck."""
        mapper = MinCutMapper(temper_layout_subset, tolerance_mm=2.0)

        # Simulate a horizontal cut between Q1/Q2 and the bus capacitor
        # This would indicate insufficient channel between power stage and bus
        min_cut_edges = [
            (("F.Cu", (25.0, 40.0)), ("F.Cu", (55.0, 40.0)), 0),
        ]

        result = mapper.map_mincut_to_components(min_cut_edges)
        refs = {b.component_ref for b in result}

        # Should identify power components as blockers
        assert len(refs & {"Q1", "Q2", "C_BUS1", "U_GATE"}) > 0

    def test_empty_space_not_blocked(self, temper_layout_subset):
        """Test that cuts in empty regions don't identify blockers."""
        mapper = MinCutMapper(temper_layout_subset, tolerance_mm=2.0)

        # Cut in empty space (far from all components)
        min_cut_edges = [
            (("F.Cu", (80.0, 80.0)), ("F.Cu", (90.0, 80.0)), 0),
        ]

        result = mapper.map_mincut_to_components(min_cut_edges)
        assert len(result) == 0
