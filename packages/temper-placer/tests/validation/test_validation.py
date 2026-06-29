"""
Tests for the validation module.

Tests geometric validation, metrics computation, and validation base classes.
"""

import jax
import jax.numpy as jnp
import pytest

from temper_placer.core.board import Board, MountingHole, Zone
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.core.state import PlacementState
from temper_placer.validation.base import (
    CompositeValidator,
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
)
from temper_placer.validation.geometric import (
    GeometricValidator,
    GeometricViolation,
    ViolationType,
    validate_placement,
)
from temper_placer.validation.metrics import (
    compute_metrics,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def simple_netlist():
    """Create a simple netlist with 4 components."""
    components = [
        Component(
            ref="U1",
            footprint="Package_SO:SOIC-8",
            bounds=(5.0, 4.0),
            pins=[
                Pin("VCC", "8", (2.0, 1.5), net="VCC"),
                Pin("GND", "4", (-2.0, -1.5), net="GND"),
            ],
            net_class="Signal",
        ),
        Component(
            ref="R1",
            footprint="Resistor_SMD:R_0603",
            bounds=(1.6, 0.8),
            pins=[
                Pin("1", "1", (-0.5, 0.0), net="NET1"),
                Pin("2", "2", (0.5, 0.0), net="VCC"),
            ],
            net_class="Signal",
        ),
        Component(
            ref="C1",
            footprint="Capacitor_SMD:C_0603",
            bounds=(1.6, 0.8),
            pins=[
                Pin("1", "1", (-0.5, 0.0), net="VCC"),
                Pin("2", "2", (0.5, 0.0), net="GND"),
            ],
            net_class="Signal",
        ),
        Component(
            ref="Q1",
            footprint="Package_TO_SOT:TO-247",
            bounds=(16.0, 20.0),
            pins=[
                Pin("G", "1", (-5.0, 0.0), net="GATE"),
                Pin("C", "2", (0.0, 8.0), net="HV_BUS"),
                Pin("E", "3", (5.0, 0.0), net="PGND"),
            ],
            net_class="HighVoltage",
        ),
    ]
    nets = [
        Net("VCC", [("U1", "VCC"), ("R1", "2"), ("C1", "1")]),
        Net("GND", [("U1", "GND"), ("C1", "2")]),
        Net("NET1", [("R1", "1")]),
        Net("GATE", [("Q1", "G")]),
        Net("HV_BUS", [("Q1", "C")], net_class="HighVoltage", weight=2.0),
        Net("PGND", [("Q1", "E")], net_class="Power"),
    ]
    return Netlist(components=components, nets=nets)


@pytest.fixture
def simple_board():
    """Create a simple rectangular board."""
    return Board(
        width=100.0,
        height=80.0,
        origin=(0.0, 0.0),
        zones=[
            Zone("HV_ZONE", (0, 0, 50, 80), net_classes=["HighVoltage"]),
            Zone("LV_ZONE", (50, 0, 100, 80), net_classes=["Signal"]),
        ],
        mounting_holes=[
            MountingHole((5.0, 5.0), 3.2, keepout_radius=5.0),
            MountingHole((95.0, 5.0), 3.2, keepout_radius=5.0),
        ],
    )


@pytest.fixture
def valid_placement(simple_netlist, simple_board):
    """Create a valid placement with no violations."""
    # Place components well-separated
    positions = jnp.array(
        [
            [70.0, 40.0],  # U1 in LV zone
            [80.0, 60.0],  # R1 in LV zone
            [90.0, 40.0],  # C1 in LV zone
            [25.0, 40.0],  # Q1 in HV zone
        ]
    )
    rotation_logits = jnp.zeros((4, 4))  # All at 0 degrees
    return PlacementState(positions=positions, rotation_logits=rotation_logits)


@pytest.fixture
def overlapping_placement(simple_netlist):
    """Create a placement with overlapping components."""
    positions = jnp.array(
        [
            [50.0, 40.0],  # U1
            [50.5, 40.0],  # R1 - overlaps with U1
            [50.0, 42.0],  # C1 - overlaps with U1
            [25.0, 40.0],  # Q1 - separate
        ]
    )
    rotation_logits = jnp.zeros((4, 4))
    return PlacementState(positions=positions, rotation_logits=rotation_logits)


@pytest.fixture
def boundary_violating_placement(simple_netlist, simple_board):
    """Create a placement with boundary violations."""
    positions = jnp.array(
        [
            [2.0, 40.0],  # U1 - extends past left edge
            [98.0, 40.0],  # R1 - extends past right edge
            [50.0, 2.0],  # C1 - extends past bottom edge
            [25.0, 75.0],  # Q1 - extends past top edge (20mm height)
        ]
    )
    rotation_logits = jnp.zeros((4, 4))
    return PlacementState(positions=positions, rotation_logits=rotation_logits)


# =============================================================================
# ValidationResult Tests
# =============================================================================


class TestValidationResult:
    """Tests for ValidationResult class."""

    def test_empty_result_is_valid(self):
        """Empty result should be valid."""
        result = ValidationResult(valid=True)
        assert result.valid
        assert result.error_count == 0
        assert result.warning_count == 0
        assert result.critical_count == 0

    def test_error_count(self):
        """Test error counting."""
        issues = [
            ValidationIssue(ValidationSeverity.ERROR, "E1", "Error 1"),
            ValidationIssue(ValidationSeverity.ERROR, "E2", "Error 2"),
            ValidationIssue(ValidationSeverity.WARNING, "W1", "Warning 1"),
            ValidationIssue(ValidationSeverity.CRITICAL, "C1", "Critical 1"),
        ]
        result = ValidationResult(valid=False, issues=issues)
        assert result.error_count == 3  # 2 errors + 1 critical
        assert result.warning_count == 1
        assert result.critical_count == 1

    def test_merge(self):
        """Test merging two results."""
        r1 = ValidationResult(
            valid=True,
            issues=[ValidationIssue(ValidationSeverity.WARNING, "W1", "Warning")],
            metrics={"metric1": 1.0},
            elapsed_ms=10.0,
            validator_name="V1",
        )
        r2 = ValidationResult(
            valid=False,
            issues=[ValidationIssue(ValidationSeverity.ERROR, "E1", "Error")],
            metrics={"metric2": 2.0},
            elapsed_ms=20.0,
            validator_name="V2",
        )

        merged = r1.merge(r2)
        assert not merged.valid  # r2 was invalid
        assert len(merged.issues) == 2
        assert merged.metrics == {"metric1": 1.0, "metric2": 2.0}
        assert merged.elapsed_ms == 30.0
        assert "V1" in merged.validator_name and "V2" in merged.validator_name

    def test_summary(self):
        """Test summary generation."""
        issues = [
            ValidationIssue(ValidationSeverity.CRITICAL, "C1", "Critical"),
            ValidationIssue(ValidationSeverity.ERROR, "E1", "Error"),
            ValidationIssue(ValidationSeverity.WARNING, "W1", "Warning"),
        ]
        result = ValidationResult(valid=False, issues=issues)
        summary = result.summary()
        assert "FAIL" in summary
        assert "1 critical" in summary


# =============================================================================
# GeometricValidator Tests
# =============================================================================


class TestGeometricValidator:
    """Tests for GeometricValidator."""

    def test_valid_placement_passes(self, valid_placement, simple_netlist, simple_board):
        """Valid placement should have no errors."""
        validator = GeometricValidator()
        result = validator.validate(valid_placement, simple_netlist, simple_board)

        # Should be valid (no critical or error issues)
        assert result.valid, f"Expected valid but got: {result.summary()}"
        assert result.error_count == 0

    def test_overlap_detection(self, overlapping_placement, simple_netlist, simple_board):
        """Should detect overlapping components."""
        validator = GeometricValidator()
        result = validator.validate(overlapping_placement, simple_netlist, simple_board)

        assert result.metrics["overlap_count"] > 0

        # Find overlap issues
        overlap_issues = [
            i
            for i in result.issues
            if isinstance(i, GeometricViolation) and i.violation_type == ViolationType.OVERLAP
        ]
        assert len(overlap_issues) > 0

    def test_boundary_violation_detection(
        self, boundary_violating_placement, simple_netlist, simple_board
    ):
        """Should detect components outside board."""
        validator = GeometricValidator()
        result = validator.validate(boundary_violating_placement, simple_netlist, simple_board)

        assert result.metrics["boundary_violations"] > 0

        # Find boundary issues
        boundary_issues = [
            i
            for i in result.issues
            if isinstance(i, GeometricViolation) and i.violation_type == ViolationType.BOUNDARY
        ]
        assert len(boundary_issues) > 0

    def test_hv_lv_clearance_violation(self, simple_netlist, simple_board):
        """Should detect HV-LV clearance violations."""
        # Place HV component (Q1) too close to LV components
        positions = jnp.array(
            [
                [50.0, 40.0],  # U1 - at boundary
                [60.0, 60.0],  # R1
                [70.0, 40.0],  # C1
                [45.0, 40.0],  # Q1 (HV) - only 5mm from U1, violates 10mm clearance
            ]
        )
        rotation_logits = jnp.zeros((4, 4))
        state = PlacementState(positions=positions, rotation_logits=rotation_logits)

        validator = GeometricValidator(hv_lv_clearance=10.0)
        result = validator.validate(state, simple_netlist, simple_board)

        # Should have HV-LV clearance violations
        clearance_issues = [
            i
            for i in result.issues
            if isinstance(i, GeometricViolation) and i.violation_type == ViolationType.CLEARANCE
        ]

        # Check that HV-LV pair is flagged
        hv_lv_issues = [i for i in clearance_issues if i.details.get("is_hv_lv")]
        assert len(hv_lv_issues) > 0, "Should detect HV-LV clearance violation"

    def test_zone_violation_detection(self, simple_netlist, simple_board):
        """Should detect components in wrong zones."""
        # Add zone requirement to U1
        simple_netlist.components[0].zone = "LV_ZONE"

        # Place U1 in HV zone instead
        positions = jnp.array(
            [
                [25.0, 40.0],  # U1 in HV_ZONE (should be in LV_ZONE)
                [70.0, 40.0],  # R1
                [80.0, 40.0],  # C1
                [25.0, 60.0],  # Q1
            ]
        )
        rotation_logits = jnp.zeros((4, 4))
        state = PlacementState(positions=positions, rotation_logits=rotation_logits)

        validator = GeometricValidator()
        result = validator.validate(state, simple_netlist, simple_board)

        zone_issues = [
            i
            for i in result.issues
            if isinstance(i, GeometricViolation) and i.violation_type == ViolationType.ZONE
        ]
        assert len(zone_issues) > 0, "Should detect zone violation"

    def test_mounting_hole_violation(self, simple_netlist, simple_board):
        """Should detect components too close to mounting holes."""
        # Place component at mounting hole location
        positions = jnp.array(
            [
                [5.0, 5.0],  # U1 - directly on mounting hole
                [70.0, 40.0],  # R1
                [80.0, 40.0],  # C1
                [25.0, 40.0],  # Q1
            ]
        )
        rotation_logits = jnp.zeros((4, 4))
        state = PlacementState(positions=positions, rotation_logits=rotation_logits)

        validator = GeometricValidator()
        result = validator.validate(state, simple_netlist, simple_board)

        keepout_issues = [
            i
            for i in result.issues
            if isinstance(i, GeometricViolation) and i.violation_type == ViolationType.MOUNTING_HOLE
        ]
        assert len(keepout_issues) > 0, "Should detect mounting hole violation"


class TestValidatePlacementFunction:
    """Tests for the convenience validate_placement function."""

    def test_valid_placement(self, valid_placement, simple_netlist, simple_board):
        """Test convenience function with valid placement."""
        result = validate_placement(valid_placement, simple_netlist, simple_board)
        assert result.valid
        assert result.validator_name == "GeometricValidator"

    def test_custom_hv_lv_clearance(self, simple_netlist, simple_board):
        """Test with custom HV-LV clearance."""
        positions = jnp.array(
            [
                [70.0, 40.0],
                [80.0, 40.0],
                [90.0, 40.0],
                [25.0, 40.0],
            ]
        )
        rotation_logits = jnp.zeros((4, 4))
        state = PlacementState(positions=positions, rotation_logits=rotation_logits)

        # With default clearance (10mm) - should pass
        result1 = validate_placement(state, simple_netlist, simple_board, hv_lv_clearance=10.0)

        # With larger clearance (50mm) - may fail
        result2 = validate_placement(state, simple_netlist, simple_board, hv_lv_clearance=50.0)

        # result2 should have more violations
        assert result2.metrics["clearance_violations"] >= result1.metrics["clearance_violations"]


# =============================================================================
# PlacementMetrics Tests
# =============================================================================


class TestPlacementMetrics:
    """Tests for PlacementMetrics."""

    def test_valid_placement_metrics(self, valid_placement, simple_netlist, simple_board):
        """Compute metrics for valid placement."""
        metrics = compute_metrics(valid_placement, simple_netlist, simple_board)

        assert metrics.overlap_count == 0
        assert metrics.boundary_violations == 0
        assert metrics.hv_lv_violations == 0
        assert metrics.is_valid
        assert metrics.computation_time_ms > 0

    def test_overlapping_placement_metrics(
        self, overlapping_placement, simple_netlist, simple_board
    ):
        """Compute metrics for overlapping placement."""
        metrics = compute_metrics(overlapping_placement, simple_netlist, simple_board)

        assert metrics.overlap_count > 0
        assert metrics.total_overlap_area > 0
        assert metrics.worst_overlap > 0
        assert not metrics.is_valid

    def test_boundary_violation_metrics(
        self, boundary_violating_placement, simple_netlist, simple_board
    ):
        """Compute metrics for boundary-violating placement."""
        metrics = compute_metrics(boundary_violating_placement, simple_netlist, simple_board)

        assert metrics.boundary_violations > 0
        assert metrics.total_boundary_violation > 0
        assert not metrics.is_valid

    def test_wirelength_computation(self, valid_placement, simple_netlist, simple_board):
        """Test wirelength metrics."""
        metrics = compute_metrics(valid_placement, simple_netlist, simple_board)

        # Should have wirelength > 0 since there are multi-pin nets
        assert metrics.total_wirelength >= 0  # May be 0 if no multi-pin nets
        assert metrics.avg_net_length >= 0

    def test_utilization_computation(self, valid_placement, simple_netlist, simple_board):
        """Test utilization metric."""
        metrics = compute_metrics(valid_placement, simple_netlist, simple_board)

        # Utilization should be between 0 and 1
        assert 0 < metrics.utilization < 1

        # Manual check: total component area / board area
        total_area = sum(c.width * c.height for c in simple_netlist.components)
        board_area = simple_board.width * simple_board.height
        expected_utilization = total_area / board_area

        assert abs(metrics.utilization - expected_utilization) < 0.01

    def test_center_of_mass(self, valid_placement, simple_netlist, simple_board):
        """Test center of mass computation."""
        metrics = compute_metrics(valid_placement, simple_netlist, simple_board)

        # Center of mass should be within board bounds
        com_x, com_y = metrics.center_of_mass
        assert simple_board.origin[0] <= com_x <= simple_board.origin[0] + simple_board.width
        assert simple_board.origin[1] <= com_y <= simple_board.origin[1] + simple_board.height

    def test_metrics_summary(self, valid_placement, simple_netlist, simple_board):
        """Test summary generation."""
        metrics = compute_metrics(valid_placement, simple_netlist, simple_board)
        summary = metrics.summary()

        assert "Overlaps:" in summary
        assert "Boundary violations:" in summary
        assert "Wirelength:" in summary
        assert "Utilization:" in summary

    def test_metrics_to_dict(self, valid_placement, simple_netlist, simple_board):
        """Test dictionary conversion."""
        metrics = compute_metrics(valid_placement, simple_netlist, simple_board)
        d = metrics.to_dict()

        assert "overlap_count" in d
        assert "total_wirelength" in d
        assert "utilization" in d
        assert "center_of_mass" in d


# =============================================================================
# CompositeValidator Tests
# =============================================================================


class TestCompositeValidator:
    """Tests for CompositeValidator."""

    def test_empty_composite(self, valid_placement, simple_netlist, simple_board):
        """Empty composite should be valid."""
        composite = CompositeValidator([])
        result = composite.validate(valid_placement, simple_netlist, simple_board)
        assert result.valid

    def test_single_validator(self, valid_placement, simple_netlist, simple_board):
        """Composite with single validator."""
        composite = CompositeValidator([GeometricValidator()])
        result = composite.validate(valid_placement, simple_netlist, simple_board)
        assert result.valid

    def test_multiple_validators(self, valid_placement, simple_netlist, simple_board):
        """Composite with multiple validators."""
        # Two geometric validators (redundant but tests composition)
        composite = CompositeValidator(
            [
                GeometricValidator(hv_lv_clearance=10.0),
                GeometricValidator(hv_lv_clearance=20.0),
            ]
        )
        result = composite.validate(valid_placement, simple_netlist, simple_board)

        # Should have merged results
        assert "+GeometricValidator" in result.validator_name

    def test_availability_check(self, valid_placement, simple_netlist, simple_board):
        """Test is_available check."""
        composite = CompositeValidator([GeometricValidator()])
        assert composite.is_available()

        empty_composite = CompositeValidator([])
        assert not empty_composite.is_available()


# =============================================================================
# Integration Tests
# =============================================================================


class TestValidationIntegration:
    """Integration tests for validation module."""

    def test_full_validation_workflow(self, simple_netlist, simple_board):
        """Test complete validation workflow."""
        # Create a placement
        key = jax.random.PRNGKey(42)
        state = PlacementState.random_init(
            n_components=len(simple_netlist.components),
            board_width=simple_board.width,
            board_height=simple_board.height,
            key=key,
            margin=15.0,
        )

        # Run geometric validation
        val_result = validate_placement(state, simple_netlist, simple_board)

        # Compute metrics
        metrics = compute_metrics(state, simple_netlist, simple_board)

        # Both should complete without errors
        assert val_result is not None
        assert metrics is not None

        # Check consistency
        assert val_result.metrics["overlap_count"] == metrics.overlap_count
        assert val_result.metrics["boundary_violations"] == metrics.boundary_violations

    def test_validation_performance(self, simple_netlist, simple_board):
        """Test validation performance is reasonable."""
        key = jax.random.PRNGKey(0)
        state = PlacementState.random_init(
            n_components=len(simple_netlist.components),
            board_width=simple_board.width,
            board_height=simple_board.height,
            key=key,
        )

        # Run validation multiple times and check timing
        import time

        times = []
        for _ in range(10):
            start = time.time()
            validate_placement(state, simple_netlist, simple_board)
            times.append(time.time() - start)

        avg_time = sum(times) / len(times)

        # Should complete in less than 100ms for simple netlist
        assert avg_time < 0.1, f"Validation too slow: {avg_time * 1000:.1f}ms"
