"""
Tests for visualization data models.

Tests the immutable dataclasses, serialization, and factory functions
in temper_placer.visualization.model.
"""

import json
import math
import pytest

from temper_placer.visualization.model import (
    Point,
    Rectangle,
    ComponentView,
    ComponentStatus,
    ZoneView,
    BoardView,
    LossDataPoint,
    LossHistory,
    Violation,
    ViolationType,
    ConstraintStatus,
    VisualizationState,
    create_component_view,
    create_board_view_from_state,
    create_loss_data_point_from_metrics,
)


class TestPoint:
    """Tests for Point dataclass."""

    def test_create_point(self):
        """Test basic point creation."""
        p = Point(x=10.5, y=20.3)
        assert p.x == 10.5
        assert p.y == 20.3

    def test_point_immutable(self):
        """Test that Point is frozen (immutable)."""
        p = Point(x=1.0, y=2.0)
        with pytest.raises(AttributeError):
            p.x = 5.0  # type: ignore

    def test_point_to_dict(self):
        """Test Point serialization."""
        p = Point(x=3.14, y=2.71)
        d = p.to_dict()
        assert d == {"x": 3.14, "y": 2.71}

    def test_point_from_tuple(self):
        """Test creating Point from tuple."""
        p = Point.from_tuple((5.0, 10.0))
        assert p.x == 5.0
        assert p.y == 10.0

    def test_point_equality(self):
        """Test Point equality comparison."""
        p1 = Point(1.0, 2.0)
        p2 = Point(1.0, 2.0)
        p3 = Point(1.0, 3.0)
        assert p1 == p2
        assert p1 != p3


class TestRectangle:
    """Tests for Rectangle dataclass."""

    def test_create_rectangle(self):
        """Test basic rectangle creation."""
        center = Point(50.0, 40.0)
        rect = Rectangle(center=center, width=10.0, height=5.0, rotation=0.0)
        assert rect.center == center
        assert rect.width == 10.0
        assert rect.height == 5.0
        assert rect.rotation == 0.0

    def test_rectangle_default_rotation(self):
        """Test rectangle with default rotation."""
        rect = Rectangle(center=Point(0, 0), width=2.0, height=1.0)
        assert rect.rotation == 0.0

    def test_rectangle_immutable(self):
        """Test that Rectangle is frozen."""
        rect = Rectangle(center=Point(0, 0), width=2.0, height=1.0)
        with pytest.raises(AttributeError):
            rect.width = 5.0  # type: ignore

    def test_rectangle_to_dict(self):
        """Test Rectangle serialization."""
        rect = Rectangle(center=Point(10.0, 20.0), width=5.0, height=3.0, rotation=45.0)
        d = rect.to_dict()
        assert d["center"] == {"x": 10.0, "y": 20.0}
        assert d["width"] == 5.0
        assert d["height"] == 3.0
        assert d["rotation"] == 45.0

    def test_rectangle_corners_no_rotation(self):
        """Test corners calculation without rotation."""
        rect = Rectangle(center=Point(10.0, 10.0), width=4.0, height=2.0, rotation=0.0)
        corners = rect.corners
        assert len(corners) == 4

        # Check corner positions (counterclockwise from bottom-left)
        expected = [
            (8.0, 9.0),  # bottom-left
            (12.0, 9.0),  # bottom-right
            (12.0, 11.0),  # top-right
            (8.0, 11.0),  # top-left
        ]
        for corner, (ex, ey) in zip(corners, expected):
            assert abs(corner.x - ex) < 1e-9
            assert abs(corner.y - ey) < 1e-9

    def test_rectangle_corners_with_rotation(self):
        """Test corners calculation with 90-degree rotation."""
        rect = Rectangle(center=Point(0.0, 0.0), width=4.0, height=2.0, rotation=90.0)
        corners = rect.corners

        # After 90-degree CCW rotation, width and height effectively swap
        # Original corners were at (-2, -1), (2, -1), (2, 1), (-2, 1)
        # After 90-deg rotation: (1, -2), (1, 2), (-1, 2), (-1, -2)
        for corner in corners:
            # All corners should be within rotated bounds
            assert abs(corner.x) <= 1.0 + 1e-9
            assert abs(corner.y) <= 2.0 + 1e-9


class TestComponentView:
    """Tests for ComponentView dataclass."""

    def test_create_component_view(self):
        """Test basic component view creation."""
        cv = ComponentView(
            ref="U1",
            position=Point(50.0, 30.0),
            rotation=90.0,
            width=10.0,
            height=8.0,
        )
        assert cv.ref == "U1"
        assert cv.position.x == 50.0
        assert cv.rotation == 90.0
        assert cv.status == ComponentStatus.OK  # default

    def test_component_view_with_status(self):
        """Test component view with error status."""
        cv = ComponentView(
            ref="R1",
            position=Point(0, 0),
            rotation=0,
            width=2.0,
            height=1.0,
            status=ComponentStatus.ERROR,
            violations=("Overlaps with R2",),
        )
        assert cv.status == ComponentStatus.ERROR
        assert len(cv.violations) == 1
        assert "Overlaps" in cv.violations[0]

    def test_component_view_immutable(self):
        """Test that ComponentView is frozen."""
        cv = ComponentView(ref="C1", position=Point(0, 0), rotation=0, width=1.0, height=1.0)
        with pytest.raises(AttributeError):
            cv.ref = "C2"  # type: ignore

    def test_component_view_to_dict(self):
        """Test ComponentView serialization."""
        cv = ComponentView(
            ref="U1",
            position=Point(10.0, 20.0),
            rotation=180.0,
            width=5.0,
            height=3.0,
            status=ComponentStatus.WARNING,
            zone="HV_ZONE",
            footprint="QFN-48",
            violations=("Near thermal source",),
        )
        d = cv.to_dict()

        assert d["ref"] == "U1"
        assert d["position"] == {"x": 10.0, "y": 20.0}
        assert d["rotation"] == 180.0
        assert d["width"] == 5.0
        assert d["height"] == 3.0
        assert d["status"] == "warning"
        assert d["zone"] == "HV_ZONE"
        assert d["footprint"] == "QFN-48"
        assert d["violations"] == ["Near thermal source"]

    def test_component_view_bounds_property(self):
        """Test bounds property returns correct Rectangle."""
        cv = ComponentView(
            ref="U1",
            position=Point(50.0, 40.0),
            rotation=45.0,
            width=10.0,
            height=8.0,
        )
        bounds = cv.bounds
        assert isinstance(bounds, Rectangle)
        assert bounds.center.x == 50.0
        assert bounds.center.y == 40.0
        assert bounds.width == 10.0
        assert bounds.rotation == 45.0


class TestComponentStatus:
    """Tests for ComponentStatus enum."""

    def test_status_values(self):
        """Test all status values exist."""
        assert ComponentStatus.OK.value == "ok"
        assert ComponentStatus.WARNING.value == "warning"
        assert ComponentStatus.ERROR.value == "error"
        assert ComponentStatus.FIXED.value == "fixed"


class TestZoneView:
    """Tests for ZoneView dataclass."""

    def test_create_zone_view(self):
        """Test basic zone view creation."""
        polygon = (Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10))
        zone = ZoneView(name="HV_KEEPOUT", polygon=polygon, zone_type="keepout")
        assert zone.name == "HV_KEEPOUT"
        assert len(zone.polygon) == 4
        assert zone.zone_type == "keepout"

    def test_zone_view_to_dict(self):
        """Test ZoneView serialization."""
        polygon = (Point(0, 0), Point(5, 0), Point(5, 5))
        zone = ZoneView(name="GROUND_ZONE", polygon=polygon, zone_type="copper", color="#00FF00")
        d = zone.to_dict()

        assert d["name"] == "GROUND_ZONE"
        assert len(d["polygon"]) == 3
        assert d["polygon"][0] == {"x": 0, "y": 0}
        assert d["zone_type"] == "copper"
        assert d["color"] == "#00FF00"


class TestBoardView:
    """Tests for BoardView dataclass."""

    def test_create_board_view(self):
        """Test basic board view creation."""
        board = BoardView(width=100.0, height=80.0)
        assert board.width == 100.0
        assert board.height == 80.0
        assert board.components == ()
        assert board.zones == ()

    def test_board_view_with_components(self):
        """Test board view with components."""
        comp1 = ComponentView(ref="U1", position=Point(10, 10), rotation=0, width=5, height=3)
        comp2 = ComponentView(ref="R1", position=Point(20, 20), rotation=90, width=2, height=1)
        board = BoardView(width=100, height=80, components=(comp1, comp2))

        assert len(board.components) == 2
        assert board.components[0].ref == "U1"
        assert board.components[1].ref == "R1"

    def test_board_view_to_dict(self):
        """Test BoardView serialization."""
        comp = ComponentView(ref="U1", position=Point(10, 10), rotation=0, width=5, height=3)
        zone = ZoneView(
            name="KEEPOUT",
            polygon=(Point(0, 0), Point(5, 0), Point(5, 5), Point(0, 5)),
        )
        board = BoardView(
            width=100,
            height=80,
            components=(comp,),
            zones=(zone,),
            title="Test Board",
        )
        d = board.to_dict()

        assert d["width"] == 100
        assert d["height"] == 80
        assert len(d["components"]) == 1
        assert d["components"][0]["ref"] == "U1"
        assert len(d["zones"]) == 1
        assert d["zones"][0]["name"] == "KEEPOUT"
        assert d["title"] == "Test Board"
        assert d["origin"] == {"x": 0.0, "y": 0.0}

    def test_board_view_to_json(self):
        """Test BoardView JSON serialization."""
        board = BoardView(width=100, height=80, title="JSON Test")
        json_str = board.to_json()

        # Parse and verify
        parsed = json.loads(json_str)
        assert parsed["width"] == 100
        assert parsed["title"] == "JSON Test"


class TestLossDataPoint:
    """Tests for LossDataPoint dataclass."""

    def test_create_loss_data_point(self):
        """Test basic loss data point creation."""
        ldp = LossDataPoint(
            epoch=100,
            total_loss=0.05,
            breakdown={"overlap": 0.02, "boundary": 0.03},
        )
        assert ldp.epoch == 100
        assert ldp.total_loss == 0.05
        assert ldp.breakdown["overlap"] == 0.02

    def test_loss_data_point_to_dict(self):
        """Test LossDataPoint serialization."""
        ldp = LossDataPoint(
            epoch=50,
            total_loss=0.1,
            breakdown={"overlap": 0.05},
            temperature=0.5,
            learning_rate=0.001,
        )
        d = ldp.to_dict()

        assert d["epoch"] == 50
        assert d["total_loss"] == 0.1
        assert d["breakdown"] == {"overlap": 0.05}
        assert d["temperature"] == 0.5
        assert d["learning_rate"] == 0.001


class TestLossHistory:
    """Tests for LossHistory dataclass (mutable)."""

    def test_create_loss_history(self):
        """Test basic loss history creation."""
        history = LossHistory()
        assert len(history.data_points) == 0
        assert history.phase_boundaries == []
        assert history.phase_names == []

    def test_add_point(self):
        """Test adding points to history."""
        history = LossHistory()
        history.add_point(LossDataPoint(epoch=0, total_loss=1.0))
        history.add_point(LossDataPoint(epoch=10, total_loss=0.5))

        assert len(history.data_points) == 2
        assert history.data_points[0].epoch == 0
        assert history.data_points[1].total_loss == 0.5

    def test_loss_history_is_mutable(self):
        """Test that LossHistory is mutable (not frozen)."""
        history = LossHistory()
        # Should not raise - LossHistory is intentionally mutable
        history.phase_boundaries = [100, 200]
        assert history.phase_boundaries == [100, 200]

    def test_epochs_property(self):
        """Test epochs property."""
        history = LossHistory()
        history.add_point(LossDataPoint(epoch=0, total_loss=1.0))
        history.add_point(LossDataPoint(epoch=50, total_loss=0.5))
        history.add_point(LossDataPoint(epoch=100, total_loss=0.1))

        assert history.epochs == [0, 50, 100]

    def test_losses_property(self):
        """Test losses property."""
        history = LossHistory()
        history.add_point(LossDataPoint(epoch=0, total_loss=1.0))
        history.add_point(LossDataPoint(epoch=50, total_loss=0.5))

        assert history.losses == [1.0, 0.5]

    def test_get_term_history(self):
        """Test getting history for specific loss term."""
        history = LossHistory()
        history.add_point(
            LossDataPoint(epoch=0, total_loss=1.0, breakdown={"overlap": 0.6, "boundary": 0.4})
        )
        history.add_point(
            LossDataPoint(epoch=10, total_loss=0.5, breakdown={"overlap": 0.3, "boundary": 0.2})
        )

        overlap_history = history.get_term_history("overlap")
        assert overlap_history == [0.6, 0.3]

        boundary_history = history.get_term_history("boundary")
        assert boundary_history == [0.4, 0.2]

    def test_get_term_history_missing_term(self):
        """Test getting history for term not in all points."""
        history = LossHistory()
        history.add_point(LossDataPoint(epoch=0, total_loss=1.0, breakdown={}))
        history.add_point(LossDataPoint(epoch=10, total_loss=0.5, breakdown={"overlap": 0.3}))

        # Missing term should return 0.0
        overlap_history = history.get_term_history("overlap")
        assert overlap_history == [0.0, 0.3]

    def test_loss_terms_property(self):
        """Test loss_terms property."""
        history = LossHistory()
        history.add_point(
            LossDataPoint(
                epoch=0,
                total_loss=1.0,
                breakdown={"overlap": 0.5, "boundary": 0.3, "wirelength": 0.2},
            )
        )

        terms = history.loss_terms
        assert set(terms) == {"overlap", "boundary", "wirelength"}

    def test_loss_terms_empty_history(self):
        """Test loss_terms with empty history."""
        history = LossHistory()
        assert history.loss_terms == []

    def test_loss_history_to_dict(self):
        """Test LossHistory serialization."""
        history = LossHistory()
        history.add_point(LossDataPoint(epoch=0, total_loss=1.0))
        history.phase_boundaries = [100]
        history.phase_names = ["warmup"]

        d = history.to_dict()
        assert len(d["data_points"]) == 1
        assert d["phase_boundaries"] == [100]
        assert d["phase_names"] == ["warmup"]

    def test_loss_history_to_json(self):
        """Test LossHistory JSON serialization."""
        history = LossHistory()
        history.add_point(LossDataPoint(epoch=0, total_loss=1.0, breakdown={"overlap": 0.5}))

        json_str = history.to_json()
        parsed = json.loads(json_str)

        assert len(parsed["data_points"]) == 1
        assert parsed["data_points"][0]["total_loss"] == 1.0


class TestViolationType:
    """Tests for ViolationType enum."""

    def test_violation_type_values(self):
        """Test all violation type values."""
        assert ViolationType.OVERLAP.value == "overlap"
        assert ViolationType.BOUNDARY.value == "boundary"
        assert ViolationType.CLEARANCE.value == "clearance"
        assert ViolationType.THERMAL.value == "thermal"
        assert ViolationType.ZONE.value == "zone"
        assert ViolationType.DRC.value == "drc"


class TestViolation:
    """Tests for Violation dataclass."""

    def test_create_violation(self):
        """Test basic violation creation."""
        v = Violation(
            violation_type=ViolationType.OVERLAP,
            severity=0.8,
            component_refs=("U1", "R1"),
            message="Components overlap by 2mm",
        )
        assert v.violation_type == ViolationType.OVERLAP
        assert v.severity == 0.8
        assert v.component_refs == ("U1", "R1")
        assert "overlap" in v.message.lower()

    def test_violation_with_location(self):
        """Test violation with location."""
        v = Violation(
            violation_type=ViolationType.BOUNDARY,
            severity=1.0,
            component_refs=("U1",),
            location=Point(105.0, 50.0),
        )
        assert v.location is not None
        assert v.location.x == 105.0

    def test_violation_to_dict(self):
        """Test Violation serialization."""
        v = Violation(
            violation_type=ViolationType.CLEARANCE,
            severity=0.5,
            component_refs=("U1", "U2"),
            message="HV clearance violation",
            location=Point(30.0, 40.0),
        )
        d = v.to_dict()

        assert d["type"] == "clearance"
        assert d["severity"] == 0.5
        assert d["components"] == ["U1", "U2"]
        assert d["message"] == "HV clearance violation"
        assert d["location"] == {"x": 30.0, "y": 40.0}

    def test_violation_to_dict_no_location(self):
        """Test Violation serialization without location."""
        v = Violation(
            violation_type=ViolationType.THERMAL,
            severity=0.3,
            component_refs=("Q1",),
        )
        d = v.to_dict()
        assert d["location"] is None


class TestConstraintStatus:
    """Tests for ConstraintStatus dataclass."""

    def test_create_constraint_status(self):
        """Test basic constraint status creation."""
        status = ConstraintStatus()
        assert status.violations == ()
        assert status.overlap_count == 0
        assert status.is_valid

    def test_constraint_status_with_violations(self):
        """Test constraint status with violations."""
        v1 = Violation(
            violation_type=ViolationType.OVERLAP, severity=0.8, component_refs=("U1", "R1")
        )
        v2 = Violation(violation_type=ViolationType.BOUNDARY, severity=1.0, component_refs=("U2",))
        status = ConstraintStatus(
            violations=(v1, v2),
            overlap_count=1,
            boundary_violations=1,
        )

        assert len(status.violations) == 2
        assert status.overlap_count == 1
        assert status.boundary_violations == 1
        assert not status.is_valid  # has critical violations

    def test_constraint_status_is_valid(self):
        """Test is_valid property."""
        # Valid - no overlaps or boundary violations
        valid = ConstraintStatus(thermal_warnings=5, clearance_violations=2)
        assert valid.is_valid  # thermal and clearance are not critical

        # Invalid - has overlap
        invalid1 = ConstraintStatus(overlap_count=1)
        assert not invalid1.is_valid

        # Invalid - has boundary violation
        invalid2 = ConstraintStatus(boundary_violations=1)
        assert not invalid2.is_valid

    def test_constraint_status_to_dict(self):
        """Test ConstraintStatus serialization."""
        v = Violation(
            violation_type=ViolationType.OVERLAP, severity=0.5, component_refs=("U1", "R1")
        )
        status = ConstraintStatus(
            violations=(v,),
            overlap_count=1,
            boundary_violations=0,
            clearance_violations=2,
            thermal_warnings=3,
            drc_errors=1,
        )
        d = status.to_dict()

        assert len(d["violations"]) == 1
        assert d["summary"]["overlap"] == 1
        assert d["summary"]["boundary"] == 0
        assert d["summary"]["clearance"] == 2
        assert d["summary"]["thermal"] == 3
        assert d["summary"]["drc"] == 1
        assert d["total_violations"] == 1
        assert d["has_errors"] is True

    def test_constraint_status_to_json(self):
        """Test ConstraintStatus JSON serialization."""
        status = ConstraintStatus(overlap_count=2)
        json_str = status.to_json()
        parsed = json.loads(json_str)

        assert parsed["summary"]["overlap"] == 2
        assert parsed["has_errors"] is True


class TestVisualizationState:
    """Tests for VisualizationState dataclass."""

    def test_create_visualization_state(self):
        """Test basic visualization state creation."""
        board = BoardView(width=100, height=80)
        history = LossHistory()
        constraints = ConstraintStatus()

        state = VisualizationState(
            board=board,
            loss_history=history,
            constraints=constraints,
            epoch=50,
            elapsed_seconds=12.5,
            is_training=True,
        )

        assert state.board.width == 100
        assert state.epoch == 50
        assert state.elapsed_seconds == 12.5
        assert state.is_training is True

    def test_visualization_state_to_dict(self):
        """Test VisualizationState serialization."""
        board = BoardView(width=100, height=80)
        history = LossHistory()
        history.add_point(LossDataPoint(epoch=0, total_loss=1.0))
        constraints = ConstraintStatus(overlap_count=1)

        state = VisualizationState(
            board=board,
            loss_history=history,
            constraints=constraints,
            epoch=100,
            elapsed_seconds=30.0,
            is_training=False,
        )
        d = state.to_dict()

        assert d["board"]["width"] == 100
        assert len(d["loss_history"]["data_points"]) == 1
        assert d["constraints"]["summary"]["overlap"] == 1
        assert d["epoch"] == 100
        assert d["elapsed_seconds"] == 30.0
        assert d["is_training"] is False

    def test_visualization_state_to_json(self):
        """Test VisualizationState JSON serialization."""
        board = BoardView(width=100, height=80)
        history = LossHistory()
        constraints = ConstraintStatus()

        state = VisualizationState(
            board=board,
            loss_history=history,
            constraints=constraints,
        )
        json_str = state.to_json()
        parsed = json.loads(json_str)

        assert "board" in parsed
        assert "loss_history" in parsed
        assert "constraints" in parsed
        assert "epoch" in parsed


class TestCreateComponentView:
    """Tests for create_component_view factory function."""

    def test_create_component_view_basic(self):
        """Test basic factory function usage."""
        cv = create_component_view(
            ref="U1",
            position=(50.0, 30.0),
            rotation_degrees=90.0,
            bounds=(10.0, 8.0),
        )

        assert cv.ref == "U1"
        assert cv.position.x == 50.0
        assert cv.position.y == 30.0
        assert cv.rotation == 90.0
        assert cv.width == 10.0
        assert cv.height == 8.0
        assert cv.status == ComponentStatus.OK

    def test_create_component_view_with_options(self):
        """Test factory function with all options."""
        cv = create_component_view(
            ref="R1",
            position=(10.0, 20.0),
            rotation_degrees=0.0,
            bounds=(2.0, 1.0),
            footprint="0805",
            status=ComponentStatus.ERROR,
            violations=["Overlaps with R2", "Too close to edge"],
        )

        assert cv.footprint == "0805"
        assert cv.status == ComponentStatus.ERROR
        assert len(cv.violations) == 2
        assert "Overlaps" in cv.violations[0]


class TestCreateBoardViewFromState:
    """Tests for create_board_view_from_state factory function."""

    def test_create_board_view_basic(self):
        """Test basic factory function usage."""
        board = create_board_view_from_state(
            board_width=100.0,
            board_height=80.0,
            component_refs=["U1", "R1", "C1"],
            positions=[(10, 20), (30, 40), (50, 60)],
            rotations=[0, 90, 180],
            bounds=[(5, 3), (2, 1), (3, 2)],
        )

        assert board.width == 100.0
        assert board.height == 80.0
        assert len(board.components) == 3

        assert board.components[0].ref == "U1"
        assert board.components[0].position.x == 10
        assert board.components[0].rotation == 0
        assert board.components[0].width == 5

        assert board.components[1].ref == "R1"
        assert board.components[1].rotation == 90

        assert board.components[2].ref == "C1"
        assert board.components[2].rotation == 180

    def test_create_board_view_with_footprints(self):
        """Test factory with footprints."""
        board = create_board_view_from_state(
            board_width=100.0,
            board_height=80.0,
            component_refs=["U1", "R1"],
            positions=[(10, 20), (30, 40)],
            rotations=[0, 90],
            bounds=[(5, 3), (2, 1)],
            footprints=["QFN-48", "0805"],
        )

        assert board.components[0].footprint == "QFN-48"
        assert board.components[1].footprint == "0805"

    def test_create_board_view_with_statuses(self):
        """Test factory with statuses."""
        board = create_board_view_from_state(
            board_width=100.0,
            board_height=80.0,
            component_refs=["U1", "R1"],
            positions=[(10, 20), (30, 40)],
            rotations=[0, 90],
            bounds=[(5, 3), (2, 1)],
            statuses=[ComponentStatus.OK, ComponentStatus.ERROR],
        )

        assert board.components[0].status == ComponentStatus.OK
        assert board.components[1].status == ComponentStatus.ERROR

    def test_create_board_view_empty(self):
        """Test factory with no components."""
        board = create_board_view_from_state(
            board_width=100.0,
            board_height=80.0,
            component_refs=[],
            positions=[],
            rotations=[],
            bounds=[],
        )

        assert board.width == 100.0
        assert len(board.components) == 0


class TestCreateLossDataPointFromMetrics:
    """Tests for create_loss_data_point_from_metrics factory function."""

    def test_create_from_mock_metrics(self):
        """Test factory function with mock metrics object."""

        # Create a mock metrics object
        class MockMetrics:
            epoch = 100
            loss = 0.05
            loss_breakdown = {"overlap": 0.02, "boundary": 0.03}
            temperature = 0.3
            learning_rate = 0.0005

        metrics = MockMetrics()
        ldp = create_loss_data_point_from_metrics(metrics)

        assert ldp.epoch == 100
        assert ldp.total_loss == 0.05
        assert ldp.breakdown == {"overlap": 0.02, "boundary": 0.03}
        assert ldp.temperature == 0.3
        assert ldp.learning_rate == 0.0005

    def test_create_from_metrics_no_breakdown(self):
        """Test factory with metrics missing breakdown."""

        class MockMetrics:
            epoch = 50
            loss = 0.1
            loss_breakdown = None
            temperature = None
            learning_rate = None

        metrics = MockMetrics()
        ldp = create_loss_data_point_from_metrics(metrics)

        assert ldp.epoch == 50
        assert ldp.total_loss == 0.1
        assert ldp.breakdown == {}
        assert ldp.temperature is None


class TestJsonRoundTrip:
    """Test JSON serialization round-trips."""

    def test_board_view_json_roundtrip(self):
        """Test that BoardView can be serialized and deserialized."""
        comp = ComponentView(
            ref="U1",
            position=Point(10.5, 20.3),
            rotation=45.0,
            width=5.0,
            height=3.0,
            status=ComponentStatus.WARNING,
        )
        zone = ZoneView(
            name="KEEPOUT",
            polygon=(Point(0, 0), Point(5, 0), Point(5, 5)),
        )
        original = BoardView(
            width=100.5,
            height=80.3,
            components=(comp,),
            zones=(zone,),
            title="Test",
        )

        # Serialize
        json_str = original.to_json()

        # Deserialize and verify structure
        parsed = json.loads(json_str)
        assert parsed["width"] == 100.5
        assert parsed["components"][0]["ref"] == "U1"
        assert parsed["components"][0]["position"]["x"] == 10.5
        assert parsed["zones"][0]["name"] == "KEEPOUT"

    def test_visualization_state_json_roundtrip(self):
        """Test full visualization state serialization."""
        board = BoardView(width=100, height=80)
        history = LossHistory()
        history.add_point(LossDataPoint(epoch=0, total_loss=1.0, breakdown={"overlap": 0.5}))
        history.add_point(LossDataPoint(epoch=100, total_loss=0.1, breakdown={"overlap": 0.05}))
        history.phase_boundaries = [50]
        history.phase_names = ["warmup"]

        constraints = ConstraintStatus(
            violations=(
                Violation(
                    violation_type=ViolationType.OVERLAP,
                    severity=0.5,
                    component_refs=("U1", "R1"),
                ),
            ),
            overlap_count=1,
        )

        state = VisualizationState(
            board=board,
            loss_history=history,
            constraints=constraints,
            epoch=100,
            elapsed_seconds=45.5,
            is_training=False,
        )

        # Serialize
        json_str = state.to_json()

        # Should be valid JSON
        parsed = json.loads(json_str)

        # Verify structure
        assert parsed["board"]["width"] == 100
        assert len(parsed["loss_history"]["data_points"]) == 2
        assert parsed["loss_history"]["phase_names"] == ["warmup"]
        assert parsed["constraints"]["summary"]["overlap"] == 1
        assert parsed["epoch"] == 100
        assert parsed["is_training"] is False
